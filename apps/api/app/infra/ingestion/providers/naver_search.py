"""Naver Search API — local (official). https://developers.naver.com/docs/serviceapi/search/local/local.md

Limits: display ≤ 5, start ≤ 5 per query, so breadth comes from many keywords × both sort modes.
The API has no stable place id, ratings or prices; review text is never fetched.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.infra.ingestion.base import NormalizedPlace, ProviderNotConfiguredError, RawPlace, RegionRef
from app.infra.ingestion.providers._common import (
    PAGE_DELAY_S,
    HttpClientMixin,
    clean,
    haversine_m,
    strip_html,
    to_float,
    valid_coord,
)

URL = "https://openapi.naver.com/v1/search/local.json"
DISPLAY = 5
MAX_START = 5
SORTS: tuple[str, ...] = ("random", "comment")  # 정확도순, 리뷰 개수순
COORD_SCALE = 1e7


def stable_external_id(title: str, address: str) -> str:
    return hashlib.sha1(f"{title}|{address}".encode()).hexdigest()[:24]


class NaverSearchProvider(HttpClientMixin):
    name = "naver_search"

    def __init__(
        self, client_id: str | None, client_secret: str | None, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if not client_id:
            raise ProviderNotConfiguredError(self.name, "NAVER_SEARCH_CLIENT_ID")
        if not client_secret:
            raise ProviderNotConfiguredError(self.name, "NAVER_SEARCH_CLIENT_SECRET")
        self._headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        self._init_client(client)

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        jobs = [(kw, sort) for kw in region.search_keywords for sort in SORTS]
        start_job = int((cursor or {}).get("query_index", 0))
        seen: set[str] = set()
        for ji in range(start_job, len(jobs)):
            keyword, sort = jobs[ji]
            start = 1
            while start <= MAX_START:
                resp = await self.client.get(
                    URL,
                    params={"query": keyword, "display": DISPLAY, "start": start, "sort": sort},
                    headers=self._headers,
                )
                resp.raise_for_status()
                body = resp.json()
                items = body.get("items", [])
                for item in items:
                    ext_id = stable_external_id(strip_html(item.get("title")), str(item.get("address", "")))
                    if ext_id in seen or not self._within_region(item, region):
                        continue
                    seen.add(ext_id)
                    yield RawPlace(provider=self.name, external_id=ext_id, raw=item)
                start += DISPLAY
                if len(items) < DISPLAY or start > int(body.get("total", 0)):
                    break
                await asyncio.sleep(PAGE_DELAY_S)
            await asyncio.sleep(PAGE_DELAY_S)

    @staticmethod
    def _coords(item: dict[str, Any]) -> tuple[float | None, float | None]:
        mapx, mapy = to_float(item.get("mapx")), to_float(item.get("mapy"))
        if mapx is None or mapy is None:
            return None, None
        return mapy / COORD_SCALE, mapx / COORD_SCALE

    def _within_region(self, item: dict[str, Any], region: RegionRef) -> bool:
        lat, lng = self._coords(item)
        if lat is None or lng is None:
            return False
        return haversine_m(region.center_lat, region.center_lng, lat, lng) <= region.radius_m * 1.5

    def normalize(self, raw: RawPlace) -> NormalizedPlace | None:
        item = raw.raw
        name = strip_html(item.get("title"))
        lat, lng = self._coords(item)
        if not name or lat is None or lng is None or not valid_coord(lat, lng):
            return None
        category = clean(item.get("category"))
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=name,
            lat=lat,
            lng=lng,
            provider_categories=[category] if category else [],
            address=clean(item.get("address")),
            road_address=clean(item.get("roadAddress")),
            phone=clean(item.get("telephone")),
            description=clean(strip_html(item.get("description"))),
        )
