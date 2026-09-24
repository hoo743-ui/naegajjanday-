"""Counting calls to external APIs that have a quota, so the operator hears before a key runs dry (docs/47).

One httpx response hook, installed once per process (API lifespan · CLI): every AsyncClient made anywhere
— link lookups, blog counts, directions, bulk ingestion — reports its responses here. The host says which
provider it was; the row for (provider, today in Asia/Seoul) is bumped. A provider that says "quota used
up" (HTTP 429, data.go.kr code 22) marks the day exhausted.

Counting must never break a request: every failure here is swallowed and logged once.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.logging import get_logger

logger = get_logger(__name__)

KST = ZoneInfo("Asia/Seoul")
QUOTAS_PATH = Path(__file__).resolve().parents[2] / "data" / "quotas.json"
# data.go.kr answers an exhausted quota with HTTP 200 and this in the body
DATA_GO_KR_EXHAUSTED = ("LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR", "<returnReasonCode>22<")

_db: Any = None
_installed = False
_warned = False


def provider_of(url: httpx.URL) -> str | None:
    host, path = url.host, url.path
    if host == "apis.data.go.kr":
        return "tourapi" if path.startswith("/B551011/") else "data_go_kr"
    if host == "api.odcloud.kr":
        return "data_go_kr"
    return {
        "dapi.kakao.com": "kakao_local",
        "apis-navi.kakaomobility.com": "kakao_mobility",
        "openapi.naver.com": "naver_search",
        "naveropenapi.apigw.ntruss.com": "naver_maps",
        "maps.apigw.ntruss.com": "naver_maps",
        "api.pexels.com": "pexels",
        "api.unsplash.com": "unsplash",
        "api.openverse.org": "openverse",
        "www.kopis.or.kr": "kopis",
        "kopis.or.kr": "kopis",
        "apis.openapi.sk.com": "tmap",
    }.get(host)


def today() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def _header_int(response: httpx.Response, *names: str) -> int | None:
    for name in names:
        value = response.headers.get(name)
        if value is not None and value.strip().isdigit():
            return int(value)
    return None


async def _exhausted(provider: str, response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if provider in {"tourapi", "data_go_kr"} and response.status_code == 200:
        head = (await response.aread())[:800].decode("utf-8", "replace")
        return any(marker in head for marker in DATA_GO_KR_EXHAUSTED)
    return False


async def _on_response(response: httpx.Response) -> None:
    global _warned
    provider = provider_of(response.request.url)
    if provider is None or _db is None:
        return
    try:
        exhausted = await _exhausted(provider, response)
        await record(
            provider,
            ok=response.status_code < 400 and not exhausted,
            exhausted=exhausted,
            remaining=_header_int(response, "x-ratelimit-remaining", "x-rate-limit-remaining"),
            limit=_header_int(response, "x-ratelimit-limit", "x-rate-limit-limit"),
        )
    except Exception as e:
        if not _warned:
            _warned = True
            logger.warning("api_usage.record_failed", provider=provider, error=str(e)[:160])


async def record(
    provider: str,
    *,
    ok: bool,
    exhausted: bool = False,
    remaining: int | None = None,
    limit: int | None = None,
) -> None:
    from app.infra.db.models import ApiUsage

    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "provider": provider,
        "day": today(),
        "calls": 1,
        "errors": 0 if ok else 1,
        "updated_at": now,
    }
    update: dict[str, Any] = {
        "calls": ApiUsage.calls + 1,
        "errors": ApiUsage.errors + (0 if ok else 1),
        "updated_at": now,
    }
    if exhausted:
        values["exhausted_at"] = update["exhausted_at"] = now
    if remaining is not None:
        values["remaining"] = update["remaining"] = remaining
    if limit is not None:
        values["limit"] = update["limit"] = limit
    insert = pg_insert if _db.dialect == "postgresql" else sqlite_insert
    stmt = insert(ApiUsage).values(**values)
    stmt = stmt.on_conflict_do_update(index_elements=["provider", "day"], set_=update)
    async with _db.engine.begin() as conn:
        await conn.execute(stmt)


def install(db: Any) -> None:
    """Every httpx.AsyncClient made after this reports its responses (after any hooks it already has)."""
    global _db, _installed
    _db = db
    if _installed:
        return
    _installed = True
    original = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        hooks = dict(kwargs.pop("event_hooks", None) or {})
        hooks["response"] = [*hooks.get("response", []), _on_response]
        original(self, *args, event_hooks=hooks, **kwargs)

    httpx.AsyncClient.__init__ = patched  # type: ignore[method-assign]


# ── the report the admin bell reads ─────────────────────────────────────────────


@lru_cache(maxsize=1)
def quotas() -> dict[str, dict[str, Any]]:
    raw = json.loads(QUOTAS_PATH.read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def status_of(used: int, limit: int | None, exhausted: bool) -> str:
    if exhausted:
        return "exhausted"
    if not limit:
        return "unknown"
    ratio = used / limit
    return "critical" if ratio >= 0.95 else "warn" if ratio >= 0.8 else "ok"


async def report(session: Any) -> list[dict[str, Any]]:
    """Every provider seen this month or configured: used in its period, limit, share, status."""
    from app.infra.db.models import ApiUsage

    day = today()
    month = day[:6]
    rows = (await session.execute(select(ApiUsage).where(ApiUsage.day >= month + "01"))).scalars().all()
    out = []
    for provider in sorted({r.provider for r in rows} | set(quotas())):
        spec = quotas().get(provider, {"name": provider, "limit": None, "period": "day"})
        period_rows = [
            r for r in rows if r.provider == provider and (spec["period"] == "month" or r.day == day)
        ]
        today_row = next((r for r in rows if r.provider == provider and r.day == day), None)
        used = sum(r.calls for r in period_rows)
        # a provider that sends its own counter is more exact than ours
        limit = (today_row.limit if today_row and today_row.limit else None) or spec.get("limit")
        if today_row and today_row.remaining is not None and limit:
            used = max(used, limit - today_row.remaining)
        exhausted = bool(today_row and today_row.exhausted_at)
        out.append(
            {
                "provider": provider,
                "name": spec["name"],
                "period": spec["period"],
                "used": used,
                "limit": limit,
                "share": round(used / limit, 3) if limit else None,
                "errors_today": today_row.errors if today_row else 0,
                "status": status_of(used, limit, exhausted),
                "verified": bool(spec.get("verified")),
                "where": spec.get("where", ""),
                "note": spec.get("note", ""),
            }
        )
    return out
