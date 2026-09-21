"""Performances near a point that really have a show inside the requested time window.

Source: the official performance open API (see `infra/ingestion/providers/kopis.py`). Without a key the
answer is `available=false` and nothing is requested. The list has no venue coordinates, so each
performance needs detail (→ venue id) and venue (→ coordinates); both are cached, the venue of a known
hall is remembered by name, and the number of uncached calls per request is capped (`partial=true`).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.showtimes import fits_window, parse_runtime_min, shows_on
from app.infra.db.models import Region
from app.infra.ingestion.dedupe import distance_m
from app.infra.ingestion.providers.kopis import KopisRules, PerformanceDetail, PerformanceSummary, Venue
from app.schemas.performance import PerformanceList, PerformanceOut, PerformanceVenue

LOCAL_TZ = timezone(timedelta(hours=9))  # showtimes are local wall-clock times
NO_KEY_REASON = "공연 정보(KOPIS) 키가 아직 설정되지 않았어요."
NO_SHOW_REASON = "이 시간대에 시작하는 공연을 주변에서 찾지 못했어요."
FAR_AWAY_DEG = 1.5  # a point this far from every known region is not in the country


class PerformanceSource(Protocol):
    rules: KopisRules
    upstream_calls: int

    @property
    def available(self) -> bool: ...
    def is_cached(self, kind: str, ident: str) -> bool: ...
    def known_venue_id(self, venue_name: str) -> str | None: ...
    async def list_performances(
        self, day_from: date, day_to: date, *, area_code: str | None = None, state: str | None = None
    ) -> list[PerformanceSummary]: ...
    async def detail(self, performance_id: str) -> PerformanceDetail | None: ...
    async def venue(self, venue_id: str) -> Venue | None: ...


class PerformanceService:
    def __init__(self, session: AsyncSession, source: PerformanceSource) -> None:
        self._s = session
        self._src = source

    async def nearby(
        self, lat: float, lng: float, radius_m: int, start_at: datetime, duration_min: int
    ) -> PerformanceList:
        rules = self._src.rules
        if not self._src.available:
            return PerformanceList(available=False, reason=NO_KEY_REASON, attribution=rules.attribution)
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=LOCAL_TZ)
        window_start = start_at.astimezone(LOCAL_TZ)
        window_end = window_start + timedelta(minutes=duration_min)
        day = window_start.date()

        summaries: dict[str, PerformanceSummary] = {}
        for code in await self._area_codes(lat, lng) or (None,):
            for row in await self._src.list_performances(day, day, area_code=code):
                summaries.setdefault(row.id, row)

        budget = _Budget(self._src, rules.max_upstream_calls_per_request)
        items: list[PerformanceOut] = []
        pending = list(summaries.values())
        for at in range(0, len(pending), rules.concurrency):
            found = await asyncio.gather(
                *(
                    self._check(row, lat, lng, radius_m, day, window_start, window_end, budget)
                    for row in pending[at : at + rules.concurrency]
                )
            )
            items.extend(item for item in found if item is not None)
        items.sort(key=lambda i: (i.show_times[0], i.venue.distance_m, i.title))
        return PerformanceList(
            items=items,
            available=True,
            reason=None if items else NO_SHOW_REASON,
            partial=budget.exhausted,
            attribution=rules.attribution,
        )

    async def _check(
        self,
        row: PerformanceSummary,
        lat: float,
        lng: float,
        radius_m: int,
        day: date,
        window_start: datetime,
        window_end: datetime,
        budget: _Budget,
    ) -> PerformanceOut | None:
        if (row.date_from and day < row.date_from) or (row.date_to and day > row.date_to):
            return None
        # a hall we already know to be too far away costs no call at all
        known_venue = self._src.known_venue_id(row.venue_name)
        if known_venue and self._src.is_cached("venue", known_venue):
            venue = await self._src.venue(known_venue)
            if venue is None or _distance(venue, lat, lng) > radius_m:
                return None
        if not budget.allow("detail", row.id):
            return None
        detail = await self._src.detail(row.id)
        if detail is None or not detail.venue_id or not budget.allow("venue", detail.venue_id):
            return None
        venue = await self._src.venue(detail.venue_id)
        if venue is None or venue.lat is None or venue.lng is None:
            return None
        distance = _distance(venue, lat, lng)
        if distance > radius_m:
            return None
        runtime = parse_runtime_min(detail.runtime_text)
        shows = shows_on(detail.showtimes_text, day, detail.date_from, detail.date_to)
        fitting = fits_window(shows, window_start, window_end, runtime)
        if not fitting:
            return None
        return PerformanceOut(
            id=detail.id,
            title=detail.title,
            genre=detail.genre or row.genre,
            venue=PerformanceVenue(
                name=venue.name or detail.venue_name,
                address=venue.address,
                lat=venue.lat,
                lng=venue.lng,
                distance_m=round(distance),
            ),
            period_from=detail.date_from,
            period_to=detail.date_to,
            show_times=[_hhmm(t) for t in fitting],
            runtime_min=runtime,
            price_text=detail.price_text,
            poster_url=detail.poster_url or row.poster_url,
            detail_url=self._src.rules.detail_url(detail.id),
        )

    async def _area_codes(self, lat: float, lng: float) -> tuple[str, ...]:
        """Nearest region → its top-level ancestor → the upstream area code(s). Unknown → no filter."""
        nearest = (
            await self._s.execute(
                select(Region.id, Region.parent_id, Region.slug, Region.center_lat, Region.center_lng)
                .where(
                    Region.center_lat.between(lat - FAR_AWAY_DEG, lat + FAR_AWAY_DEG),
                    Region.center_lng.between(lng - FAR_AWAY_DEG, lng + FAR_AWAY_DEG),
                )
                .order_by(
                    (Region.center_lat - lat) * (Region.center_lat - lat)
                    + (Region.center_lng - lng) * (Region.center_lng - lng) * 0.64
                )
                .limit(1)
            )
        ).first()
        if nearest is None:
            return ()
        slug, parent_id = nearest.slug, nearest.parent_id
        for _ in range(4):  # hotspot → 시군구 → 시도
            if parent_id is None:
                break
            parent = (
                await self._s.execute(select(Region.slug, Region.parent_id).where(Region.id == parent_id))
            ).first()
            if parent is None:
                break
            slug, parent_id = parent.slug, parent.parent_id
        return tuple(self._src.rules.area_codes_by_sido_slug.get(slug, ()))


class _Budget:
    """Caps the UNCACHED upstream calls of one request; cached lookups are always allowed."""

    def __init__(self, source: PerformanceSource, limit: int) -> None:
        self._src = source
        self._left = limit
        self.exhausted = False

    def allow(self, kind: str, ident: str) -> bool:
        if self._src.is_cached(kind, ident):
            return True
        if self._left <= 0:
            self.exhausted = True
            return False
        self._left -= 1
        return True


def _distance(venue: Venue, lat: float, lng: float) -> float:
    if venue.lat is None or venue.lng is None:
        return float("inf")
    return distance_m(lat, lng, venue.lat, venue.lng)


def _hhmm(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"
