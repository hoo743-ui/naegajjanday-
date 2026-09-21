"""Kakao Local REST API (official). https://developers.kakao.com/docs/latest/ko/local/dev-guide

The API exposes no ratings, prices or reviews — those fields stay None.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.infra.ingestion.base import NormalizedPlace, ProviderNotConfiguredError, RawPlace, RegionRef
from app.infra.ingestion.providers._common import PAGE_DELAY_S, HttpClientMixin, clean, to_float, valid_coord

BASE_URL = "https://dapi.kakao.com"
KEYWORD_PATH = "/v2/local/search/keyword.json"
CATEGORY_PATH = "/v2/local/search/category.json"
CATEGORY_GROUP_CODES: tuple[str, ...] = ("FD6", "CE7", "AT4", "CT1")  # 음식점, 카페, 관광명소, 문화시설
MAX_PAGE = 45
PAGE_SIZE = 15
MAX_RADIUS_M = 20_000


class KakaoLocalProvider(HttpClientMixin):
    name = "kakao_local"

    def __init__(self, rest_api_key: str | None, *, client: httpx.AsyncClient | None = None) -> None:
        if not rest_api_key:
            raise ProviderNotConfiguredError(self.name, "KAKAO_REST_API_KEY")
        self._headers = {"Authorization": f"KakaoAK {rest_api_key}"}
        self._init_client(client)

    def _queries(self, region: RegionRef) -> list[tuple[str, dict[str, str]]]:
        queries: list[tuple[str, dict[str, str]]] = [
            (KEYWORD_PATH, {"query": kw}) for kw in region.search_keywords
        ]
        queries += [(CATEGORY_PATH, {"category_group_code": code}) for code in CATEGORY_GROUP_CODES]
        return queries

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        queries = self._queries(region)
        start_query = int((cursor or {}).get("query_index", 0))
        start_page = int((cursor or {}).get("page", 1))
        seen: set[str] = set()
        geo = {
            "x": f"{region.center_lng:.7f}",
            "y": f"{region.center_lat:.7f}",
            "radius": str(min(region.radius_m, MAX_RADIUS_M)),
            "size": str(PAGE_SIZE),
        }
        for qi in range(start_query, len(queries)):
            path, params = queries[qi]
            page = start_page if qi == start_query else 1
            while page <= MAX_PAGE:
                resp = await self.client.get(
                    BASE_URL + path, params={**params, **geo, "page": str(page)}, headers=self._headers
                )
                resp.raise_for_status()
                body = resp.json()
                for doc in body.get("documents", []):
                    ext_id = str(doc.get("id") or "")
                    if not ext_id or ext_id in seen:
                        continue
                    seen.add(ext_id)
                    yield RawPlace(provider=self.name, external_id=ext_id, raw=doc)
                if body.get("meta", {}).get("is_end", True):
                    break
                page += 1
                await asyncio.sleep(PAGE_DELAY_S)

    def normalize(self, raw: RawPlace) -> NormalizedPlace | None:
        doc = raw.raw
        lat, lng = to_float(doc.get("y")), to_float(doc.get("x"))
        name = clean(doc.get("place_name"))
        if not name or lat is None or lng is None or not valid_coord(lat, lng):
            return None
        categories = [
            c for c in (clean(doc.get("category_group_code")), clean(doc.get("category_name"))) if c
        ]
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=name,
            lat=lat,
            lng=lng,
            provider_categories=categories,
            address=clean(doc.get("address_name")),
            road_address=clean(doc.get("road_address_name")),
            phone=clean(doc.get("phone")),
        )
