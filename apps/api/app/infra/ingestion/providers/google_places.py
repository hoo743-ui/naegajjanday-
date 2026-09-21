"""Google Places API (New) — official. https://developers.google.com/maps/documentation/places/web-service

Only aggregate rating fields are requested; review text is deliberately NOT in the field mask (terms).
`priceLevel` is an ordinal, not KRW — it is never converted into `price_per_person`.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.infra.ingestion.base import (
    NormalizedHour,
    NormalizedPlace,
    ProviderNotConfiguredError,
    RawPlace,
    RegionRef,
)
from app.infra.ingestion.providers._common import PAGE_DELAY_S, HttpClientMixin, clean, to_float, valid_coord

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_FIELDS: tuple[str, ...] = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.primaryType",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.regularOpeningHours",
    "places.nationalPhoneNumber",
)
NEARBY_TYPE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("restaurant",),
    ("cafe", "bakery"),
    ("bar",),
    ("tourist_attraction", "park"),
    ("museum", "art_gallery"),
)
MAX_NEARBY_RADIUS_M = 50_000
MAX_TEXT_PAGES = 3  # API caps text search at 60 results


def google_day_to_dow(day: int) -> int:
    """Google: 0=Sunday … 6=Saturday → ours: 0=Monday … 6=Sunday."""
    return (day + 6) % 7


def _hhmm(point: dict[str, Any]) -> str:
    return f"{int(point.get('hour', 0)):02d}:{int(point.get('minute', 0)):02d}"


def parse_opening_hours(regular: dict[str, Any] | None) -> list[NormalizedHour]:
    periods = (regular or {}).get("periods") or []
    if not periods:
        return []
    if len(periods) == 1 and "close" not in periods[0]:  # open 24/7
        return [NormalizedHour(dow=d, open_time="00:00", close_time="00:00") for d in range(7)]
    by_day: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for period in periods:
        open_pt, close_pt = period.get("open"), period.get("close")
        if not open_pt or not close_pt:
            continue
        by_day[google_day_to_dow(int(open_pt.get("day", 0)))].append((_hhmm(open_pt), _hhmm(close_pt)))
    hours: list[NormalizedHour] = []
    for dow in range(7):
        spans = sorted(by_day.get(dow, []))
        if not spans:
            hours.append(NormalizedHour(dow=dow, is_closed=True))
            continue
        hour = NormalizedHour(dow=dow, open_time=spans[0][0], close_time=spans[-1][1])
        if len(spans) >= 2:  # split shifts → break time between first close and next open
            hour.break_start, hour.break_end = spans[0][1], spans[1][0]
        hours.append(hour)
    return hours


class GooglePlacesProvider(HttpClientMixin):
    name = "google_places"

    def __init__(self, api_key: str | None, *, client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise ProviderNotConfiguredError(self.name, "GOOGLE_PLACES_API_KEY")
        self._api_key = api_key
        self._init_client(client)

    def _headers(self, *, paged: bool) -> dict[str, str]:
        fields = PLACE_FIELDS + (("nextPageToken",) if paged else ())
        return {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": ",".join(fields),
            "Content-Type": "application/json",
        }

    async def fetch(self, region: RegionRef, cursor: dict[str, Any] | None = None) -> AsyncIterator[RawPlace]:
        circle = {
            "center": {"latitude": region.center_lat, "longitude": region.center_lng},
            "radius": float(min(region.radius_m, MAX_NEARBY_RADIUS_M)),
        }
        seen: set[str] = set()
        phase = str((cursor or {}).get("phase", "nearby"))
        start_index = int((cursor or {}).get("index", 0))

        if phase == "nearby":
            for types in NEARBY_TYPE_GROUPS[start_index:]:
                body = {
                    "includedTypes": list(types),
                    "maxResultCount": 20,
                    "locationRestriction": {"circle": circle},
                    "languageCode": "ko",
                    "regionCode": "KR",
                }
                resp = await self.client.post(NEARBY_URL, json=body, headers=self._headers(paged=False))
                resp.raise_for_status()
                for raw in self._emit(resp.json(), seen):
                    yield raw
                await asyncio.sleep(PAGE_DELAY_S)
            start_index = 0

        for keyword in region.search_keywords[start_index:]:
            token: str | None = None
            for _ in range(MAX_TEXT_PAGES):
                body = {
                    "textQuery": keyword,
                    "pageSize": 20,
                    "locationBias": {"circle": circle},
                    "languageCode": "ko",
                    "regionCode": "KR",
                }
                if token:
                    body["pageToken"] = token
                resp = await self.client.post(TEXT_URL, json=body, headers=self._headers(paged=True))
                resp.raise_for_status()
                payload = resp.json()
                for raw in self._emit(payload, seen):
                    yield raw
                token = payload.get("nextPageToken")
                if not token:
                    break
                await asyncio.sleep(PAGE_DELAY_S)

    def _emit(self, payload: dict[str, Any], seen: set[str]) -> list[RawPlace]:
        out: list[RawPlace] = []
        for place in payload.get("places", []):
            ext_id = str(place.get("id") or "")
            if ext_id and ext_id not in seen:
                seen.add(ext_id)
                out.append(RawPlace(provider=self.name, external_id=ext_id, raw=place))
        return out

    def normalize(self, raw: RawPlace) -> NormalizedPlace | None:
        place = raw.raw
        location = place.get("location") or {}
        lat, lng = to_float(location.get("latitude")), to_float(location.get("longitude"))
        name = clean((place.get("displayName") or {}).get("text"))
        if not name or lat is None or lng is None or not valid_coord(lat, lng):
            return None
        primary = clean(place.get("primaryType"))
        types = [t for t in place.get("types", []) if isinstance(t, str)]
        categories = ([primary] if primary else []) + [t for t in types if t != primary]
        rating = to_float(place.get("rating"))
        return NormalizedPlace(
            provider=self.name,
            external_id=raw.external_id,
            name=name,
            lat=lat,
            lng=lng,
            provider_categories=categories,
            address=clean(place.get("formattedAddress")),
            phone=clean(place.get("nationalPhoneNumber")),
            opening_hours=parse_opening_hours(place.get("regularOpeningHours")),
            rating_avg=rating,
            rating_count=int(place.get("userRatingCount") or 0) if rating is not None else 0,
        )
