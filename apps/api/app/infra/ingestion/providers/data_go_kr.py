"""공공데이터포털(data.go.kr) 표준데이터셋 generic reader — official Open API.

One class serves any standard dataset: the dataset URL and the column mapping are configuration.
Standard datasets are nationwide, so rows are filtered by distance to the region center.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.infra.ingestion.base import NormalizedPlace, ProviderNotConfiguredError, RawPlace, RegionRef
from app.infra.ingestion.providers._common import (
    PAGE_DELAY_S,
    HttpClientMixin,
    clean,
    haversine_m,
    to_float,
    valid_coord,
)

NUM_OF_ROWS = 1000
MAX_PAGES = 200
REQUIRED_FIELDS: tuple[str, ...] = ("name", "lat", "lng")

# 전국도시공원정보표준데이터
CITY_PARK_DATASET_URL = "http://api.data.go.kr/openapi/tn_pubr_public_cty_park_info_api"
CITY_PARK_FIELD_MAP: dict[str, str] = {
    "external_id": "manageNo",
    "name": "parkNm",
    "lat": "latitude",
    "lng": "longitude",
    "address": "lnmadr",
    "road_address": "rdnmadr",
    "phone": "phoneNumber",
}


def extract_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    body = (payload.get("response") or {}).get("body") or {}
    total = int(body.get("totalCount") or 0)
    items = body.get("items")
    if isinstance(items, dict):  # some datasets wrap rows as {"item": [...]}
        items = items.get("item")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return [], total
    return [row for row in items if isinstance(row, dict)], total


class DataGoKrProvider(HttpClientMixin):
    name = "data_go_kr"

    def __init__(
        self,
        service_key: str | None,
        dataset_url: str,
        field_map: dict[str, str],
        *,
        is_free: bool = False,
        category_hint: str | None = None,
        extra_params: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not service_key:
            raise ProviderNotConfiguredError(self.name, "DATA_GO_KR_SERVICE_KEY")
        missing = [f for f in REQUIRED_FIELDS if f not in field_map]
        if missing:
            raise ValueError(f"field_map is missing required canonical fields: {missing}")
        self._service_key = service_key
        self._dataset_url = dataset_url
        self._field_map = dict(field_map)
        self._is_free = is_free
        self._category_hint = category_hint
        self._extra_params = dict(extra_params or {})
        self._init_client(client)

    def _get(self, row: dict[str, Any], field: str) -> Any:
        column = self._field_map.get(field)
        return row.get(column) if column else None

    def _external_id(self, row: dict[str, Any]) -> str | None:
        explicit = clean(self._get(row, "external_id"))
        if explicit:
            return explicit
        name, lat, lng = clean(self._get(row, "name")), self._get(row, "lat"), self._get(row, "lng")
        return f"{name}@{lat},{lng}" if name else None

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        page = int((cursor or {}).get("page", 1))
        seen: set[str] = set()
        while page <= MAX_PAGES:
            params = {
                **self._extra_params,
                "serviceKey": self._service_key,
                "pageNo": str(page),
                "numOfRows": str(NUM_OF_ROWS),
                "type": "json",
            }
            resp = await self.client.get(self._dataset_url, params=params)
            resp.raise_for_status()
            rows, total = extract_rows(resp.json())
            for row in rows:
                lat, lng = to_float(self._get(row, "lat")), to_float(self._get(row, "lng"))
                ext_id = self._external_id(row)
                if lat is None or lng is None or ext_id is None or ext_id in seen:
                    continue
                if haversine_m(region.center_lat, region.center_lng, lat, lng) > region.radius_m * 1.5:
                    continue
                seen.add(ext_id)
                yield RawPlace(provider=self.name, external_id=ext_id, raw=row)
            if not rows or page * NUM_OF_ROWS >= total:
                return
            page += 1
            await asyncio.sleep(PAGE_DELAY_S)

    def normalize(self, raw: RawPlace) -> NormalizedPlace | None:
        row = raw.raw
        name = clean(self._get(row, "name"))
        lat, lng = to_float(self._get(row, "lat")), to_float(self._get(row, "lng"))
        if not name or lat is None or lng is None or not valid_coord(lat, lng):
            return None
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=name,
            lat=lat,
            lng=lng,
            provider_categories=[self._category_hint] if self._category_hint else [],
            address=clean(self._get(row, "address")),
            road_address=clean(self._get(row, "road_address")),
            phone=clean(self._get(row, "phone")),
            description=clean(self._get(row, "description")),
            is_free=self._is_free,
        )
