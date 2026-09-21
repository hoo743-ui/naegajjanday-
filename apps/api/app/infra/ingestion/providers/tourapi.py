"""한국관광공사 TourAPI 4.0 (KorService2) — official. https://www.data.go.kr/data/15101578/openapi.do

Use the *Decoding* service key from data.go.kr (httpx URL-encodes query params itself).
`region.area_code` format: "areaCode" or "areaCode:sigunguCode" (e.g. "1:13" = 서울 마포구).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import httpx

from app.infra.ingestion.base import (
    NormalizedEvent,
    NormalizedPlace,
    ProviderNotConfiguredError,
    RawPlace,
    RegionRef,
)
from app.infra.ingestion.providers._common import (
    PAGE_DELAY_S,
    HttpClientMixin,
    clean,
    haversine_m,
    to_float,
    valid_coord,
)

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
AREA_LIST_OP = "areaBasedList2"
FESTIVAL_OP = "searchFestival2"
NUM_OF_ROWS = 100
MAX_PAGES = 50
FESTIVAL_CONTENT_TYPE = "15"


def parse_area_code(area_code: str | None) -> tuple[str | None, str | None]:
    if not area_code:
        return None, None
    area, _, sigungu = area_code.partition(":")
    return area.strip() or None, sigungu.strip() or None


def extract_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """TourAPI quirks: `items` is "" when empty, and `item` is a dict when there is exactly one."""
    body = (payload.get("response") or {}).get("body") or {}
    items = body.get("items")
    total = int(body.get("totalCount") or 0)
    if not isinstance(items, dict):
        return [], total
    item = items.get("item")
    if isinstance(item, dict):
        return [item], total
    if isinstance(item, list):
        return [i for i in item if isinstance(i, dict)], total
    return [], total


def _parse_yyyymmdd(value: Any) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except ValueError:
        return None


class TourApiProvider(HttpClientMixin):
    name = "tourapi"

    def __init__(
        self,
        service_key: str | None,
        *,
        client: httpx.AsyncClient | None = None,
        festivals_from: date | None = None,
    ) -> None:
        if not service_key:
            raise ProviderNotConfiguredError(self.name, "TOURAPI_SERVICE_KEY")
        self._service_key = service_key
        self._festivals_from = festivals_from
        self._init_client(client)

    def _base_params(self, region: RegionRef) -> dict[str, str]:
        params = {
            "serviceKey": self._service_key,
            "MobileOS": "ETC",
            "MobileApp": "naegajjanday",
            "_type": "json",
            "numOfRows": str(NUM_OF_ROWS),
            "arrange": "C",
        }
        area, sigungu = parse_area_code(region.area_code)
        if area:
            params["areaCode"] = area
        if area and sigungu:
            params["sigunguCode"] = sigungu
        return params

    async def _pages(
        self, operation: str, params: dict[str, str], start_page: int
    ) -> AsyncIterator[list[dict[str, Any]]]:
        page = start_page
        while page <= MAX_PAGES:
            resp = await self.client.get(f"{BASE_URL}/{operation}", params={**params, "pageNo": str(page)})
            resp.raise_for_status()
            items, total = extract_items(resp.json())
            if items:
                yield items
            if not items or page * NUM_OF_ROWS >= total:
                return
            page += 1
            await asyncio.sleep(PAGE_DELAY_S)

    def _in_region(self, item: dict[str, Any], region: RegionRef) -> bool:
        lat, lng = to_float(item.get("mapy")), to_float(item.get("mapx"))
        if lat is None or lng is None:
            return False
        return haversine_m(region.center_lat, region.center_lng, lat, lng) <= region.radius_m * 1.5

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        phase = str((cursor or {}).get("phase", "places"))
        start_page = int((cursor or {}).get("page", 1))
        base = self._base_params(region)

        if phase == "places":
            async for items in self._pages(AREA_LIST_OP, base, start_page):
                for item in items:
                    ext_id = str(item.get("contentid") or "")
                    if not ext_id or not self._in_region(item, region):
                        continue
                    if str(item.get("contenttypeid")) == FESTIVAL_CONTENT_TYPE:
                        continue  # festivals come from searchFestival2 with their dates
                    yield RawPlace(provider=self.name, external_id=ext_id, raw=item)
            start_page = 1

        since = self._festivals_from or date.today()
        festival_params = {**base, "eventStartDate": since.strftime("%Y%m%d")}
        async for items in self._pages(FESTIVAL_OP, festival_params, start_page):
            for item in items:
                ext_id = str(item.get("contentid") or "")
                if ext_id and self._in_region(item, region):
                    yield RawPlace(provider=self.name, external_id=ext_id, raw=item, kind="event")

    @staticmethod
    def _categories(item: dict[str, Any]) -> list[str]:
        keys = ("cat3", "cat2", "cat1")  # most specific first
        cats = [c for c in (clean(item.get(k)) for k in keys) if c]
        content_type = clean(item.get("contenttypeid"))
        return cats + ([f"contenttype:{content_type}"] if content_type else [])

    def normalize(self, raw: RawPlace) -> NormalizedPlace | NormalizedEvent | None:
        item = raw.raw
        lat, lng = to_float(item.get("mapy")), to_float(item.get("mapx"))
        title = clean(item.get("title"))
        if not title or lat is None or lng is None or not valid_coord(lat, lng):
            return None
        address = " ".join(p for p in (clean(item.get("addr1")), clean(item.get("addr2"))) if p) or None
        images = [u for u in (clean(item.get("firstimage")), clean(item.get("firstimage2"))) if u]

        if raw.kind == "event":
            starts, ends = (
                _parse_yyyymmdd(item.get("eventstartdate")),
                _parse_yyyymmdd(item.get("eventenddate")),
            )
            if starts is None:
                return None
            return NormalizedEvent(
                provider=self.name,
                external_id=raw.external_id,
                title=title,
                lat=lat,
                lng=lng,
                starts_on=starts,
                ends_on=ends or starts,
                provider_categories=self._categories(item),
                address=address,
                images=images,
            )
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=title,
            lat=lat,
            lng=lng,
            provider_categories=self._categories(item),
            address=address,
            phone=clean(item.get("tel")),
            thumbnail_url=images[0] if images else None,
            images=images,
        )
