"""Route Intelligence (docs/27): a generated course → a real, checked route.

course stops → canonical locations (reuse coordinates; geocode only when missing, cached)
→ legs grouped by mode → measured geometry (walk: OSRM foot router · car: NAVER Directions 5/15 when keys
exist · transit: the engine's estimate, said so) → validation (route_check) → one model for map, cards, sheet.

Nothing here invents a time: a leg is `naver`/`osrm` (measured), `estimate` (the engine's straight-line ×
detour figure, labelled as such) or `unavailable`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.cache import Cache
from app.core.config import Settings
from app.domain.models import GeoPoint, OpeningPeriod, TransportMode
from app.domain.routing.route_check import CheckLeg, CheckStop, check_route, has_coordinates
from app.infra.routing.naver_maps import NaverMapsClient, NaverMapsError
from app.schemas import route as dto
from app.services.directions_service import DirectionsService

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class RouteInputStop:
    sequence: int
    place_id: str
    name: str
    address: str | None
    lat: float | None
    lng: float | None
    arrive_at: datetime
    leave_at: datetime
    price: int
    opening_hours: Sequence[OpeningPeriod]
    # the leg that arrives here (None for the first stop)
    mode: TransportMode
    hop_to: str | None
    est_minutes: int
    est_distance_m: int


def _key(prefix: str, points: Sequence[GeoPoint]) -> str:
    raw = ";".join(f"{p.lat:.5f},{p.lng:.5f}" for p in points)
    return f"route:{prefix}:{hashlib.sha1(raw.encode()).hexdigest()[:20]}"


class RouteService:
    def __init__(
        self,
        settings: Settings,
        cache: Cache,
        directions: DirectionsService | None = None,
        naver: NaverMapsClient | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._directions = directions or DirectionsService(settings)
        self._naver = naver or NaverMapsClient(settings)

    # --- canonical locations -------------------------------------------------------------------
    async def _locate(self, stop: RouteInputStop) -> GeoPoint | None:
        if has_coordinates(stop.lat, stop.lng):
            return GeoPoint(stop.lat, stop.lng)  # type: ignore[arg-type]
        if not stop.address or not self._naver.configured:
            return None
        key = "geo:" + hashlib.sha1(stop.address.encode()).hexdigest()[:20]
        cached = await self._cache.get(key)
        if cached:
            return GeoPoint(cached[0], cached[1])
        try:
            found = await self._naver.geocode(stop.address)
        except NaverMapsError as exc:
            log.warning("route.geocode_failed", error=str(exc)[:160])
            return None
        if found is not None:
            await self._cache.set(key, [found.lat, found.lng], self._settings.geocode_cache_ttl_s)
        return found

    # --- legs ---------------------------------------------------------------------------------
    @staticmethod
    def _estimate(stop: RouteInputStop, a: GeoPoint | None, b: GeoPoint | None) -> dict[str, Any]:
        return {
            "distance_m": stop.est_distance_m,
            "duration_min": max(1, stop.est_minutes),
            "path": [(a.lat, a.lng), (b.lat, b.lng)] if a and b else [],
            "source": "estimate",
            "geometry": "straight" if a and b else "none",
        }

    async def _walk(self, points: list[GeoPoint]) -> list[dict[str, Any]] | None:
        result = await self._directions.walk(points)
        if result.get("source") != "osrm":
            return None
        return [
            {
                "distance_m": leg["distance_m"],
                "duration_min": leg["duration_min"],
                "path": [tuple(c) for c in leg["coordinates"]],
                "source": "osrm",
                "geometry": "road",
            }
            for leg in result["legs"]
        ]

    async def _drive(self, points: list[GeoPoint]) -> list[dict[str, Any]] | None:
        if not self._naver.configured:
            return None
        key = _key("car", points)
        cached = await self._cache.get(key)
        if cached:
            rows: list[dict[str, Any]] = list(cached)
            return [{**row, "path": [tuple(c) for c in row["path"]]} for row in rows]
        try:
            driven = await self._naver.driving(points)
        except NaverMapsError as exc:
            log.warning("route.naver_failed", error=str(exc)[:160], code=exc.code)
            return None
        legs: list[dict[str, Any]] = [
            {
                "distance_m": d.distance_m,
                "duration_min": d.duration_min,
                "path": d.path,
                "source": "naver",
                "geometry": "road",
            }
            for d in driven
        ]
        await self._cache.set(
            key,
            [{**leg, "path": [list(p) for p in leg["path"]]} for leg in legs],
            self._settings.route_cache_ttl_car_s,
        )
        return legs

    async def build(
        self, course_id: str, transport: TransportMode, stops: Sequence[RouteInputStop]
    ) -> dto.CourseRouteOut:
        points = [await self._locate(s) for s in stops]
        legs: list[dict[str, Any]] = []
        # group consecutive legs with the same mode and known ends → one provider call per group
        i = 1
        while i < len(stops):
            mode = stops[i].mode
            j = i
            while (
                j + 1 < len(stops)
                and stops[j + 1].mode == mode
                and points[j] is not None
                and points[j + 1] is not None
            ):
                j += 1
            group = list(range(i, j + 1))  # indices of the stops the legs arrive at
            ends = [points[group[0] - 1], *[points[k] for k in group]]
            measured: list[dict[str, Any]] | None = None
            if all(p is not None for p in ends):
                pts = [p for p in ends if p is not None]
                if mode == "walk":
                    measured = await self._walk(pts)
                elif mode == "car":
                    measured = await self._drive(pts)
            for n, k in enumerate(group):
                a, b = points[k - 1], points[k]
                leg: dict[str, Any]
                if a is None or b is None:
                    leg = {
                        "distance_m": None,
                        "duration_min": None,
                        "path": [],
                        "source": "unavailable",
                        "geometry": "none",
                    }
                elif measured is not None and n < len(measured):
                    leg = measured[n]
                else:
                    leg = self._estimate(stops[k], a, b)
                legs.append(
                    {
                        **leg,
                        "from_seq": stops[k - 1].sequence,
                        "to_seq": stops[k].sequence,
                        "origin": stops[k - 1].name,
                        "destination": stops[k].name,
                        "mode": mode,
                        "hop_to": stops[k].hop_to,
                    }
                )
            i = j + 1

        check = check_route(
            [
                CheckStop(
                    s.sequence,
                    s.place_id,
                    s.name,
                    p.lat if p else s.lat,
                    p.lng if p else s.lng,
                    s.arrive_at,
                    s.leave_at,
                    s.opening_hours,
                )
                for s, p in zip(stops, points, strict=True)
            ],
            [
                CheckLeg(
                    leg["from_seq"],
                    leg["to_seq"],
                    leg["mode"],
                    leg["duration_min"],
                    leg["distance_m"],
                    leg["source"],
                    hop=bool(leg["hop_to"]),
                )
                for leg in legs
            ],
        )
        measured_all = all(leg["source"] in ("naver", "osrm") for leg in legs)
        return dto.CourseRouteOut(
            course_id=course_id,
            transport=transport,
            stops=[
                dto.RouteStopOut(
                    sequence=s.sequence,
                    place_id=s.place_id,
                    name=s.name,
                    address=s.address,
                    lat=p.lat if p else None,
                    lng=p.lng if p else None,
                    arrive_at=s.arrive_at,
                    leave_at=s.leave_at,
                    stay_min=max(0, round((s.leave_at - s.arrive_at).total_seconds() / 60)),
                    price=s.price,
                )
                for s, p in zip(stops, points, strict=True)
            ],
            legs=[dto.RouteLegOut.model_validate(leg) for leg in legs],
            totals=dto.RouteTotals(
                travel_min=sum(leg["duration_min"] or 0 for leg in legs),
                distance_m=sum(leg["distance_m"] or 0 for leg in legs),
                measured=measured_all,
            ),
            issues=[
                dto.RouteIssueOut(code=x.code, severity=x.severity, message=x.message, stop=x.stop, leg=x.leg)
                for x in check.issues
            ],
            feasible=check.feasible,
            providers=dto.RouteProviders(
                walk="osrm" if self._settings.osrm_foot_url else "estimate",
                car="naver" if self._naver.configured else "estimate",
            ),
            computed_at=datetime.now(UTC),
        )
