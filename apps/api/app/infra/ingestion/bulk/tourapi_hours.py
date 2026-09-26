"""Real opening hours for tourism places from TourAPI `detailIntro2` (docs/55, gap A1 in docs/51).

One call per place against a 1,000-a-day key, so this is a queue worked through a little every day:

- **which first**: TourAPI places a course actually uses — inside one of the 55 hotspot neighbourhoods
  (`data/regions/intros.json`) before the rest, museums and galleries (CULTURE) before sights
  (ATTRACTION · NIGHTVIEW) before leisure/shops (ACTIVITY), the more popular first.
- **where it stopped**: the answer is stored on the place's `place_source` row (`raw.intro`: the fields,
  when, what the parser made of them). A place with `raw.intro` is done, so the next run simply continues —
  on any machine whose DB has the rows, with no separate progress file to lose.
- **how many today**: never more than `--limit`, never past what the quota hook (docs/47) says is left
  minus a reserve for the site's own TourAPI lookups; it stops at once if TourAPI says the quota is gone.
- **what is stored**: the parser (`hours_text`) is conservative. Parsed → seven `opening_hour` rows, which
  win over the category defaults. Ambiguous → nothing, the raw text stays in `raw.intro`, the defaults stay.
  Hours a place already had from elsewhere are not overwritten.

Answers can be exported to a small JSON (`export`) and loaded elsewhere with no calls (`load_file`), and
re-parsed after a parser change with no calls (`reapply`).
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import API_ROOT
from app.infra import api_usage
from app.infra.db.models import ApiUsage, Category, OpeningHour, Place, PlaceSource, PlaceStats, Region
from app.infra.db.session import Database
from app.infra.default_hours import get_default_hours
from app.infra.ingestion.bulk import tourapi_bulk
from app.infra.ingestion.hours_text import FIELDS, ParsedHours, parse_item
from app.infra.ingestion.pipeline import parse_time
from app.infra.ingestion.providers.tourapi import BASE_URL, extract_items

Log = Callable[[str], None]

PROVIDER = tourapi_bulk.PROVIDER
OPERATION = "detailIntro2"
CONTENT_TYPES = ("12", "14", "28", "38")  # 관광지 · 문화시설 · 레포츠 · 쇼핑
ROLE_ORDER = {"CULTURE": 0, "ATTRACTION": 1, "NIGHTVIEW": 1, "ACTIVITY": 2}
INTROS_FILE = API_ROOT / "data" / "regions" / "intros.json"
SHOW_VENUES = ("culture.cinema",)  # 영화 · 공연장
SHOW_LATEST_MIN = 21 * 60
DEFAULT_RESERVE = 100  # calls left for the running site (둘러보기 links) after a batch
BATCH = 20
CALL_GAP_S = 0.15
LOCK_RETRIES = 20
LOCK_WAIT_S = 3.0
KEEP_FIELDS = (
    "usefee",
    "usefeeleports",
    "parking",
    "parkingculture",
    "parkingleports",
    "parkingshopping",
    "chkbabycarriage",
    "chkbabycarriageculture",
    "chkpet",
    "chkpetculture",
    "infocenter",
    "infocenterculture",
    "spendtime",
    "expagerange",
)


class HoursIngestError(RuntimeError):
    pass


class QuotaExhausted(HoursIngestError):
    pass


@dataclass(slots=True)
class HoursReport:
    queued: int = 0
    calls: int = 0
    fetched: int = 0
    parsed: int = 0
    ambiguous: int = 0
    empty: int = 0
    missing: int = 0  # TourAPI has no intro for that id any more
    kept_existing: int = 0  # the place already had hours from another source
    remaining: int | None = None
    stopped: str | None = None
    reasons: Counter[str] = field(default_factory=Counter)

    def count(self, parsed: ParsedHours | None) -> None:
        if parsed is None:
            self.missing += 1
        elif parsed.ok:
            self.parsed += 1
        elif parsed.status == "empty":
            self.empty += 1
        else:
            self.ambiguous += 1
            self.reasons[(parsed.reason or "?").split(":")[0]] += 1

    def line(self) -> str:
        head = (
            f"queued={self.queued} calls={self.calls} fetched={self.fetched} parsed={self.parsed} "
            f"ambiguous={self.ambiguous} empty={self.empty} missing={self.missing} "
            f"kept_existing={self.kept_existing} remaining={self.remaining}"
        )
        tail = f" stopped={self.stopped}" if self.stopped else ""
        reasons = ", ".join(f"{k}={v}" for k, v in self.reasons.most_common(8))
        return head + tail + (f"\n  ambiguous by reason: {reasons}" if reasons else "")


@dataclass(slots=True)
class Target:
    source_id: int
    place_id: int
    content_id: str
    content_type: str
    name: str
    category_code: str
    role: str
    address: str | None
    lat: float
    lng: float
    popularity: float
    raw: dict[str, Any]
    has_hours: bool = False
    hotspot: bool = False

    def priority(self) -> tuple[int, int, float, int]:
        return (0 if self.hotspot else 1, ROLE_ORDER.get(self.role, 3), -self.popularity, self.place_id)


# ── the queue ───────────────────────────────────────────────────────────────────────────────────────


def hotspot_slugs(path: Path = INTROS_FILE) -> list[str]:
    return [k for k in json.loads(path.read_text("utf-8")) if not k.startswith("_")]


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dy = (lat2 - lat1) * 111_320
    dx = (lng2 - lng1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


async def _hotspots(session: AsyncSession) -> list[tuple[float, float, float]]:
    rows = await session.execute(
        select(Region.center_lat, Region.center_lng, Region.radius_m).where(Region.slug.in_(hotspot_slugs()))
    )
    return [(lat, lng, float(max(radius, 800))) for lat, lng, radius in rows]


async def targets(session: AsyncSession, *, with_intro: bool | None = False) -> list[Target]:
    """TourAPI places of the course roles, highest priority first. `with_intro`: False = still to fetch,
    True = already fetched, None = both."""
    rows = await session.execute(
        select(
            PlaceSource.id,
            Place.id,
            PlaceSource.external_id,
            PlaceSource.raw,
            Place.name,
            Category.code,
            Category.course_role,
            Place.road_address,
            Place.address,
            Place.lat,
            Place.lng,
            PlaceStats.popularity,
        )
        .join(Place, Place.id == PlaceSource.place_id)
        .join(Category, Category.id == Place.category_id)
        .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
        .where(
            PlaceSource.provider == PROVIDER,
            Place.status == "approved",
            Category.course_role.in_(list(ROLE_ORDER)),
        )
    )
    out: list[Target] = []
    for sid, pid, cid, raw, name, code, role, road, addr, lat, lng, pop in rows:
        raw = dict(raw or {})
        ctype = str(raw.get("contenttypeid") or "")
        if ctype not in CONTENT_TYPES:
            continue
        if with_intro is not None and ("intro" in raw) != with_intro:
            continue
        out.append(
            Target(sid, pid, str(cid), ctype, name, code, role, road or addr, lat, lng, pop or 0.0, raw)
        )
    spots = await _hotspots(session)
    # few places have hours at all (0.1 %), so the whole set is small
    with_hours = set((await session.scalars(select(OpeningHour.place_id).distinct())).all())
    for t in out:
        t.hotspot = any(_distance_m(t.lat, t.lng, la, ln) <= r for la, ln, r in spots)
        t.has_hours = t.place_id in with_hours
    out.sort(key=Target.priority)
    return out


# ── quota ───────────────────────────────────────────────────────────────────────────────────────────


async def quota_left(session: AsyncSession) -> int | None:
    """What the quota hook (docs/47) says is left of today's TourAPI calls; None = unknown limit."""
    row = await session.get(ApiUsage, (PROVIDER, api_usage.today()))
    limit = (row.limit if row and row.limit else None) or api_usage.quotas().get(PROVIDER, {}).get("limit")
    if row and row.exhausted_at:
        return 0
    if not limit:
        return None
    used = row.calls if row else 0
    if row and row.remaining is not None:
        used = max(used, int(limit) - row.remaining)
    return max(0, int(limit) - used)


# ── fetching ────────────────────────────────────────────────────────────────────────────────────────


def _intro_of(item: Mapping[str, Any] | None, content_type: str, fetched_at: str) -> dict[str, Any]:
    use_key, rest_key = FIELDS.get(content_type, ("usetime", "restdate"))
    if item is None:
        return {"fetched_at": fetched_at, "missing": True, "fields": {}}
    keep = {k: item.get(k) for k in (use_key, rest_key, *KEEP_FIELDS) if k and item.get(k)}
    return {"fetched_at": fetched_at, "fields": keep}


async def fetch_one(
    client: httpx.AsyncClient, key: str, content_id: str, content_type: str
) -> tuple[dict[str, Any] | None, int | None]:
    """The intro item (None = TourAPI has none) and the rate-limit header's remaining count."""
    resp = await client.get(
        f"{BASE_URL}/{OPERATION}",
        params={
            "serviceKey": key,
            "MobileOS": "ETC",
            "MobileApp": "naegajjanday",
            "_type": "json",
            "contentId": content_id,
            "contentTypeId": content_type,
        },
    )
    remaining = api_usage._header_int(resp, "x-ratelimit-remaining")
    if resp.status_code == 429 or any(m in resp.text[:800] for m in api_usage.DATA_GO_KR_EXHAUSTED):
        raise QuotaExhausted("TourAPI says today's quota is used up")
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:
        raise HoursIngestError(resp.text.replace(key, "***")[:300]) from exc
    header = (payload.get("response") or {}).get("header") or {}
    code = str(header.get("resultCode") or "")
    if code == "22":
        raise QuotaExhausted("TourAPI result code 22 (quota)")
    if code != "0000":
        raise HoursIngestError(f"{code}: {header.get('resultMsg')}")
    items, _ = extract_items(payload)
    return (items[0] if items else None), remaining


# ── writing ─────────────────────────────────────────────────────────────────────────────────────────


def default_closed(t: Target) -> list[int]:
    return [p.dow for p in get_default_hours().for_place(t.category_code, t.name, t.address) if p.is_closed]


def _late_close(parsed: ParsedHours) -> int:
    """The latest closing minute of any open day (past midnight counts as late)."""
    latest = 0
    for d in parsed.days:
        if d.is_closed or not d.open_time or not d.close_time:
            continue
        o, c = (int(x[:2]) * 60 + int(x[3:5]) for x in (d.open_time, d.close_time))
        latest = max(latest, c if c > o else c + 1440)
    return latest


def parse_intro(t: Target, intro: Mapping[str, Any]) -> ParsedHours | None:
    if intro.get("missing"):
        return None
    parsed = parse_item(
        t.content_type,
        dict(intro.get("fields") or {}),
        default_closed=default_closed(t),
        place_name=t.name,
        category_code=t.category_code,
    )
    # a theatre's "이용시간" is its box office (09:00~18:00); the shows are at night — storing it would
    # shut every evening performance out, so the category default stays
    if parsed.ok and t.category_code.startswith(SHOW_VENUES) and _late_close(parsed) < SHOW_LATEST_MIN:
        return ParsedHours("ambiguous", reason="show venue: office hours, not show times")
    return parsed


async def apply(session: AsyncSession, t: Target, intro: dict[str, Any], report: HoursReport) -> None:
    """Store the answer on the source row and, when the parser understood it, the place's hours."""
    parsed = parse_intro(t, intro)
    report.count(parsed)
    applied_before = bool((t.raw.get("intro") or {}).get("applied"))
    intro = {**intro, "status": "missing" if parsed is None else parsed.status, "applied": False}
    if parsed is not None and not parsed.ok:
        intro["reason"] = parsed.reason
        if applied_before:  # an earlier parser stored hours this one no longer trusts
            await session.execute(delete(OpeningHour).where(OpeningHour.place_id == t.place_id))
    if parsed is not None and parsed.ok:
        if t.has_hours and not applied_before:
            report.kept_existing += 1
            intro["kept_existing"] = True
        else:
            await session.execute(delete(OpeningHour).where(OpeningHour.place_id == t.place_id))
            session.add_all(
                OpeningHour(
                    place_id=t.place_id,
                    dow=d.dow,
                    open_time=parse_time(d.open_time),
                    close_time=parse_time(d.close_time),
                    break_start=parse_time(d.break_start),
                    break_end=parse_time(d.break_end),
                    is_closed=d.is_closed,
                )
                for d in parsed.days
            )
            intro["applied"] = True
            intro["closed_from"] = parsed.closed_from
    t.raw = {**t.raw, "intro": intro}
    await session.execute(update(PlaceSource).where(PlaceSource.id == t.source_id).values(raw=t.raw))


def _is_locked(exc: BaseException) -> bool:
    return "database is locked" in str(exc).lower()


async def _write(
    session: AsyncSession, done: Sequence[tuple[Target, dict[str, Any]]], report: HoursReport
) -> None:
    """Apply a batch in one transaction; another job holding the SQLite write lock → wait and redo."""
    before = [dict(t.raw) for t, _ in done]
    for attempt in range(1, LOCK_RETRIES + 1):
        trial = HoursReport()
        try:
            for t, intro in done:
                await apply(session, t, intro, trial)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            for (t, _), raw in zip(done, before, strict=True):
                t.raw = raw
            if not _is_locked(exc) or attempt == LOCK_RETRIES:
                raise
            await asyncio.sleep(LOCK_WAIT_S)
            continue
        for name in ("parsed", "ambiguous", "empty", "missing", "kept_existing"):
            setattr(report, name, getattr(report, name) + getattr(trial, name))
        report.reasons.update(trial.reasons)
        return


async def run(
    db: Database,
    key: str | None,
    *,
    limit: int = 900,
    reserve: int = DEFAULT_RESERVE,
    log: Log = print,
    transport: httpx.AsyncBaseTransport | None = None,
) -> HoursReport:
    """Fetch the next `limit` places of the queue (fewer if the quota says so) and store their hours."""
    if not key:
        raise HoursIngestError("TOURAPI_SERVICE_KEY is not set")
    report = HoursReport()
    async with db.sessionmaker() as session:
        queue = await targets(session, with_intro=False)
        report.queued = len(queue)
        left = await quota_left(session)
        await session.commit()  # no transaction held while calling out (the quota hook writes too)
        budget = limit if left is None else min(limit, left - reserve)
        log(
            f"queue={len(queue)} (hotspot {sum(t.hotspot for t in queue)}) · quota left today={left} "
            f"reserve={reserve} → budget={max(budget, 0)}"
        )
        if budget <= 0:
            report.stopped = "no quota left today"
            report.remaining = left
            return report
        todo = queue[:budget]
        async with httpx.AsyncClient(timeout=30, transport=transport) as client:
            for start in range(0, len(todo), BATCH):
                done: list[tuple[Target, dict[str, Any]]] = []
                for t in todo[start : start + BATCH]:
                    try:
                        item, remaining = await fetch_one(client, key, t.content_id, t.content_type)
                    except QuotaExhausted as exc:
                        report.stopped = str(exc)
                        break
                    except (httpx.HTTPError, HoursIngestError) as exc:
                        report.calls += 1
                        log(f"  {t.content_id} {t.name}: {str(exc)[:120]}")
                        continue
                    report.calls += 1
                    report.fetched += 1
                    report.remaining = remaining
                    done.append((t, _intro_of(item, t.content_type, datetime.now(UTC).isoformat())))
                    if remaining is not None and remaining <= reserve:
                        report.stopped = f"rate-limit header says {remaining} left (reserve {reserve})"
                        break
                    await asyncio.sleep(CALL_GAP_S if transport is None else 0)
                await _write(session, done, report)
                log(f"  {start + len(done)}/{len(todo)} parsed={report.parsed} ambiguous={report.ambiguous}")
                if report.stopped:
                    break
    return report


async def reapply(db: Database, *, log: Log = print) -> HoursReport:
    """Re-parse every stored answer (after a parser change) — no calls."""
    report = HoursReport()
    async with db.sessionmaker() as session:
        done = [(t, dict(t.raw["intro"])) for t in await targets(session, with_intro=True)]
        report.queued = len(done)
        for start in range(0, len(done), 500):
            await _write(session, done[start : start + 500], report)
    log(report.line())
    return report


# ── shipping the answers (no calls on the other side) ───────────────────────────────────────────────


async def export(db: Database, out: Path, *, log: Log = print) -> int:
    async with db.sessionmaker() as session:
        done = await targets(session, with_intro=True)
    rows = [
        {
            "contentid": t.content_id,
            "contenttypeid": t.content_type,
            "fetched_at": t.raw["intro"].get("fetched_at"),
            "missing": bool(t.raw["intro"].get("missing")),
            "fields": t.raw["intro"].get("fields") or {},
        }
        for t in done
    ]
    _write_json(out, {"provider": PROVIDER, "operation": OPERATION, "intros": rows})
    log(f"{len(rows)} answers → {out}")
    return len(rows)


def _write_json(out: Path, payload: Mapping[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _intros_by_id(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(r["contentid"]): {
            "fetched_at": r.get("fetched_at"),
            "fields": dict(r.get("fields") or {}),
            **({"missing": True} if r.get("missing") else {}),
        }
        for r in data.get("intros", [])
    }


async def load_file(db: Database, path: Path, *, log: Log = print) -> HoursReport:
    """Store answers fetched elsewhere (an `export` file) — no calls. A place already answered is only
    replaced by a newer answer."""
    answers = _intros_by_id(_read_json(path))
    report = HoursReport()
    async with db.sessionmaker() as session:
        todo: list[tuple[Target, dict[str, Any]]] = []
        for t in await targets(session, with_intro=None):
            got = answers.get(t.content_id)
            if got is None:
                continue
            mine = t.raw.get("intro") or {}
            if mine and str(mine.get("fetched_at") or "") >= str(got.get("fetched_at") or ""):
                continue
            todo.append((t, got))
        report.queued = len(todo)
        for start in range(0, len(todo), 500):
            await _write(session, todo[start : start + 500], report)
    log(report.line())
    return report


def summarize(targets_: Iterable[Target]) -> Counter[str]:
    return Counter(str((t.raw.get("intro") or {}).get("status") or "todo") for t in targets_)
