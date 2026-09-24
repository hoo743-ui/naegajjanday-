"""What other people and public bodies say about a place — only what can be checked (docs/46).

We have no star ratings and store no review text (docs/19: data we do not have is not shown). What we do
have are signals with a named source, each one a fact the visitor can verify:

- visited     "성동구에서 사람들이 가장 많이 찾아간 곳 2위" — TMAP navigation destinations (measured, monthly)
- designated  모범음식점 (지자체 지정) · 백년가게 (중소벤처기업부) · 착한가격업소 (행정안전부) · 관광공사 소개
- long_run    영업 신고 30년 넘은 곳 — licence date (it carries over on a change of owner, so
              we say what the record says, not "the same family for 30 years")
- blog        블로그 후기 N건 — Naver Search API total for "<구> <이름>"
              (only with NAVER_SEARCH_CLIENT_ID/SECRET; the count and a link, never post text)

Everything except the blog count comes from our own tables, so a whole course is one query.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.models import Place, PlaceSource, PlaceTag, Tag

logger = get_logger(__name__)

SignalKind = Literal["visited", "designated", "long_run", "blog"]
BLOG_TTL_S = 7 * 24 * 3600
NAVER_BLOG = "https://openapi.naver.com/v1/search/blog.json"

# tag name → (label, source). The tags are written by ingestion (docs/13 · official_marks · visit_hubs).
TAG_SIGNALS: dict[str, tuple[SignalKind, str, str]] = {
    "모범음식점": ("designated", "모범음식점", "지자체 지정"),
    "백년가게": ("designated", "백년가게", "중소벤처기업부 지정"),
    "30년 넘은 집": ("long_run", "영업 신고 30년 넘은 곳", "지자체 인허가 기록"),
}
# provider of a place_source row → signal
SOURCE_SIGNALS: dict[str, tuple[SignalKind, str, str]] = {
    "goodprice": ("designated", "착한가격업소", "행정안전부 지정"),
    "tourapi": ("designated", "관광공사 소개", "한국관광공사 관광정보"),
    "centurystore": ("designated", "백년가게", "중소벤처기업부 지정"),
}
ORDER: dict[str, int] = {"visited": 0, "blog": 1, "designated": 2, "long_run": 3}


class Signal(BaseModel):
    kind: SignalKind
    label: str
    source: str
    url: str | None = None


class SignalMap(BaseModel):
    """place public_id → its signals, strongest first. Places without any are left out."""

    items: dict[str, list[Signal]]


def visited_signal(raw: dict[str, Any]) -> Signal | None:
    rank, district = raw.get("rank"), raw.get("district")
    if not isinstance(rank, int) or rank < 1 or not district:
        return None
    month = str(raw.get("month") or "")
    when = f" ({month[:4]}년 {int(month[4:6])}월)" if len(month) == 6 and month.isdigit() else ""
    label = (
        f"{district}에서 사람들이 가장 많이 찾아간 곳"
        if rank == 1
        else f"{district}에서 사람들이 찾아간 곳 {rank}위"
    )
    return Signal(kind="visited", label=label, source=f"티맵 내비게이션 목적지 실측{when}")


def order(signals: Iterable[Signal]) -> list[Signal]:
    seen: set[str] = set()
    out = []
    for s in sorted(signals, key=lambda s: ORDER[s.kind]):
        if s.label not in seen:  # 백년가게 can come from a tag and a source row
            seen.add(s.label)
            out.append(s)
    return out


class SignalService:
    def __init__(self, session: AsyncSession, settings: Settings, cache: Cache) -> None:
        self._s = session
        self._settings = settings
        self._cache = cache

    async def for_places(self, public_ids: list[str]) -> SignalMap:
        if not public_ids:
            return SignalMap(items={})
        rows = (
            await self._s.execute(
                select(Place.id, Place.public_id, Place.name, Place.address, Place.road_address).where(
                    Place.public_id.in_(public_ids)
                )
            )
        ).all()
        by_id = {r.id: r for r in rows}
        found: dict[int, list[Signal]] = {pid: [] for pid in by_id}
        tags = await self._s.execute(
            select(PlaceTag.place_id, Tag.name)
            .join(Tag, Tag.id == PlaceTag.tag_id)
            .where(PlaceTag.place_id.in_(list(by_id)), Tag.name.in_(list(TAG_SIGNALS)))
        )
        for pid, name in tags:
            kind, label, source = TAG_SIGNALS[name]
            found[pid].append(Signal(kind=kind, label=label, source=source))
        sources = await self._s.execute(
            select(PlaceSource.place_id, PlaceSource.provider, PlaceSource.raw).where(
                PlaceSource.place_id.in_(list(by_id)),
                PlaceSource.provider.in_([*SOURCE_SIGNALS, "tmap_hub"]),
            )
        )
        for pid, provider, raw in sources:
            if provider == "tmap_hub":
                data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                if (s := visited_signal(data)) is not None:
                    found[pid].append(s)
            else:
                kind, label, source = SOURCE_SIGNALS[provider]
                found[pid].append(Signal(kind=kind, label=label, source=source))
        blogs = await self._blog_counts([by_id[pid] for pid in by_id])
        for pid, blog in blogs.items():
            if blog is not None:
                found[pid].append(blog)
        return SignalMap(items={by_id[pid].public_id: order(sig) for pid, sig in found.items() if sig})

    async def _blog_counts(self, rows: list[Any]) -> dict[int, Signal | None]:
        cid, secret = self._settings.naver_search_client_id, self._settings.naver_search_client_secret
        if not cid or not secret or not rows:
            return {}
        async with httpx.AsyncClient(
            timeout=3.0, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
        ) as client:
            results = await asyncio.gather(*(self._blog_count(client, r) for r in rows))
        return {r.id: s for r, s in zip(rows, results, strict=True)}

    async def _blog_count(self, client: httpx.AsyncClient, row: Any) -> Signal | None:
        parts = (row.road_address or row.address or "").split()
        query = " ".join(x for x in (parts[1] if len(parts) > 1 else "", row.name) if x)
        key = f"blog:{query}"
        if (hit := await self._cache.get(key)) is not None:
            total = int(hit)
        else:
            try:
                r = await client.get(NAVER_BLOG, params={"query": query, "display": 1})
                r.raise_for_status()
                total = int(r.json().get("total") or 0)
            except (httpx.HTTPError, ValueError) as e:
                logger.warning("signals.blog_failed", error=str(e)[:120])
                return None
            await self._cache.set(key, total, BLOG_TTL_S)
        if total < 5:  # a handful of hits is noise (same-name shops elsewhere), not a reputation
            return None
        return Signal(
            kind="blog",
            label=f"블로그 후기 {total:,}건",
            source="네이버 블로그 검색",
            url=f"https://search.naver.com/search.naver?where=blog&query={quote(query + ' 후기')}",
        )
