"""가는 김에 (docs/51 B1): find the place the user has to go anyway — ours first, then Kakao's search.

A Kakao result is only used to answer this search (name, address, point) and to plan around that point;
it is never written into our places (Kakao Local terms: no database of their results).
"""

from __future__ import annotations

import math
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.infra.db.models import Place

KAKAO_KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"
CACHE_TTL_S = 24 * 3600
logger = get_logger(__name__)


def _near(a: tuple[float, float], b: tuple[float, float], metres: float = 120.0) -> bool:
    dy = (a[0] - b[0]) * 111_000
    dx = (a[1] - b[1]) * 111_000 * math.cos(math.radians(a[0]))
    return (dx * dx + dy * dy) ** 0.5 <= metres


class SpotService:
    def __init__(self, session: AsyncSession, settings: Settings, cache: Cache) -> None:
        self._s = session
        self._settings = settings
        self._cache = cache

    async def lookup(self, q: str, limit: int = 8) -> list[dict[str, Any]]:
        q = q.strip()
        if len(q) < 2:
            return []
        key = f"spots:{q}:{limit}"
        if (cached := await self._cache.get(key)) is not None:
            return list(cached)
        ours = await self._ours(q, limit)
        theirs = [
            k
            for k in await self._kakao(q, limit)
            if not any(_near((k["lat"], k["lng"]), (o["lat"], o["lng"])) for o in ours)
        ]
        found = (ours + theirs)[:limit]
        await self._cache.set(key, found, CACHE_TTL_S)
        return found

    async def _ours(self, q: str, limit: int) -> list[dict[str, Any]]:
        rows = (
            await self._s.execute(
                select(Place.public_id, Place.name, Place.road_address, Place.address, Place.lat, Place.lng)
                .where(Place.status == "approved", Place.name.contains(q))
                .order_by(func.length(Place.name), Place.name)
                .limit(max(1, limit // 2))
            )
        ).all()
        return [
            {"name": n, "address": ra or a, "lat": lat, "lng": lng, "place_id": pid, "source": "ours"}
            for pid, n, ra, a, lat, lng in rows
        ]

    async def _kakao(self, q: str, limit: int) -> list[dict[str, Any]]:
        key = self._settings.kakao_rest_api_key
        if not key:
            return []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    KAKAO_KEYWORD,
                    params={"query": q, "size": str(min(15, limit))},
                    headers={"Authorization": f"KakaoAK {key}"},
                )
            resp.raise_for_status()
            docs = resp.json().get("documents") or []
        except (httpx.HTTPError, ValueError):
            logger.warning("spots.kakao_failed", q=q)
            return []
        return [
            {
                "name": str(d.get("place_name") or ""),
                "address": d.get("road_address_name") or d.get("address_name") or None,
                "lat": float(d["y"]),
                "lng": float(d["x"]),
                "place_id": None,
                "source": "kakao",
            }
            for d in docs
            if d.get("place_name") and d.get("x") and d.get("y")
        ]
