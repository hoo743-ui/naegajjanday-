"""Places worth a stop on the way between two stops of a finished course (docs/46).

Read-only and outside the engine: the course is not changed; the result screen shows these on the line
that joins two stops ("가는 길에"). Only places people really go to — TMAP navigation popularity — and only
ones a short detour away from the straight walk between the stops.

    detour = |A→P| + |P→B| − |A→B|   (straight lines × WALK_FACTOR, in walking minutes)

Legs that are not walked (transit · car) or longer than MAX_LEG_M are skipped: there is no "on the way" on
a subway ride.
"""

from __future__ import annotations

import hashlib
import json
import math
from itertools import pairwise
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors
from app.core.cache import Cache
from app.domain.media import name_similarity
from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Category, Course, CourseStop, Event, Place, PlaceSource, PlaceStats
from app.infra.tagging import get_tag_rules
from app.schemas.course import PlaceBrief
from app.services.signal_service import Signal, visited_signal

ROLES = ("ATTRACTION", "CULTURE", "NIGHTVIEW", "ACTIVITY")
MIN_POPULARITY = 0.3  # the top 70 % of each district's measured destinations
# measured popularity is thin in shopping streets (TMAP counts drives: hotels win) → places the tourism
# organization lists count too, ranked after the measured ones
WALK_M_PER_MIN = 67.0
WALK_FACTOR = 1.25  # streets are not straight lines
MAX_DETOUR_MIN = 8
MAX_OFF_ROUTE_M = 250
MAX_LEG_M = 3_000
PER_LEG = 2
SAME_NAME = 0.75
SCAN_CAP = 300
TTL_S = 600


class AlongItem(BaseModel):
    place: PlaceBrief
    detour_min: int = Field(description="들렀다 가면 더 걷는 시간(분, 직선 기준 추정)")
    line: str = Field(description="한 줄: '가는 길에 3분 더 · 성동구에서 사람들이 찾아간 곳 2위'")
    source: str | None = Field(default=None, description="인기 순위의 출처")


class AlongLeg(BaseModel):
    from_position: int = Field(description="0 = 출발지")
    to_position: int
    items: list[AlongItem]


class AlongList(BaseModel):
    legs: list[AlongLeg]


def detour_m(a: GeoPoint, b: GeoPoint, p: GeoPoint) -> float:
    return haversine_m(a, p) + haversine_m(p, b) - haversine_m(a, b)


def off_route_m(a: GeoPoint, b: GeoPoint, p: GeoPoint) -> float:
    """Distance from P to the segment AB (equirectangular — fine at a few km)."""
    k = math.cos(math.radians((a.lat + b.lat) / 2)) * 111_320.0
    ax, ay, bx, by, px, py = (
        a.lng * k,
        a.lat * 111_320.0,
        b.lng * k,
        b.lat * 111_320.0,
        p.lng * k,
        p.lat * 111_320.0,
    )
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def detour_minutes(metres: float) -> int:
    return max(1, round(metres * WALK_FACTOR / WALK_M_PER_MIN))


class AlongService:
    def __init__(self, session: AsyncSession, cache: Cache) -> None:
        self._s = session
        self._cache = cache

    async def for_course(self, public_id: str) -> AlongList:
        course = (
            await self._s.execute(
                select(Course)
                .where(Course.public_id == public_id)
                .options(
                    selectinload(Course.stops).selectinload(CourseStop.place),
                    selectinload(Course.stops).selectinload(CourseStop.event),
                )
            )
        ).scalar_one_or_none()
        if course is None:
            raise errors.CourseNotFound()
        points: list[tuple[int, GeoPoint, int | None]] = [
            (0, GeoPoint(course.origin_lat, course.origin_lng), None)
        ]
        for s in sorted(course.stops, key=lambda s: s.position):
            where: Place | Event | None = s.place or s.event
            if where is not None:
                points.append((s.position, GeoPoint(where.lat, where.lng), s.place_id))
        state = hashlib.sha256(
            "|".join(f"{p}:{g.lat:.5f},{g.lng:.5f}" for p, g, _ in points).encode()
        ).hexdigest()
        key = f"along:{public_id}:{state[:16]}"
        if (hit := await self._cache.get(key)) is not None:
            return AlongList.model_validate(hit)
        out = await self._compute(course, points) if course.transport == "walk" else AlongList(legs=[])
        await self._cache.set(key, out.model_dump(mode="json"), TTL_S)
        return out

    async def _compute(self, course: Course, points: list[tuple[int, GeoPoint, int | None]]) -> AlongList:
        in_course = {pid for _, _, pid in points if pid is not None}
        role_ids = list(
            (await self._s.scalars(select(Category.id).where(Category.course_role.in_(ROLES)))).all()
        )
        used: set[int] = set()
        # the same place is often in the data twice ("천마총" · "천마총(대릉원)") → a name that reads
        # like a stop or an earlier pick is the same place
        seen = [s.place.name for s in course.stops if s.place]
        seen += [s.event.title for s in course.stops if s.event]
        legs: list[AlongLeg] = []
        for (pa, a, _), (pb, b, _) in pairwise(points):
            if not role_ids or haversine_m(a, b) > MAX_LEG_M or haversine_m(a, b) < 150:
                continue
            found = await self._near_leg(a, b, role_ids)
            pool: list[tuple[Place, float, float, bool]] = []
            for place, popularity, curated in found:
                if place.id in in_course or place.id in used:
                    continue
                p = GeoPoint(place.lat, place.lng)
                extra = detour_m(a, b, p)
                if off_route_m(a, b, p) > MAX_OFF_ROUTE_M or detour_minutes(extra) > MAX_DETOUR_MIN:
                    continue
                pool.append((place, popularity, extra, curated))
            # the most visited first, then the listed ones; a shorter detour breaks ties
            pool.sort(key=lambda t: (-t[1], not t[3], t[2]))
            picked: list[tuple[Place, float, float, bool]] = []
            for cand in pool:
                if len(picked) == PER_LEG:
                    break
                if any(name_similarity(cand[0].name, n) >= SAME_NAME for n in seen):
                    continue
                picked.append(cand)
                seen.append(cand[0].name)
            used.update(p.id for p, *_ in picked)
            if picked:
                ranks = await self._ranks([p.id for p, *_ in picked])
                legs.append(
                    AlongLeg(
                        from_position=pa,
                        to_position=pb,
                        items=[
                            self._item(p, extra, ranks.get(p.id), curated) for p, _, extra, curated in picked
                        ],
                    )
                )
        return AlongList(legs=legs)

    async def _near_leg(
        self, a: GeoPoint, b: GeoPoint, role_ids: list[int]
    ) -> list[tuple[Place, float, bool]]:
        pad_lat = MAX_OFF_ROUTE_M / 111_320.0
        pad_lng = pad_lat / max(0.01, math.cos(math.radians(a.lat)))
        listed = exists().where(PlaceSource.place_id == Place.id, PlaceSource.provider == "tourapi")
        popularity = func.coalesce(PlaceStats.popularity, 0.0)
        stmt = (
            select(Place, popularity, listed)
            .outerjoin(PlaceStats, PlaceStats.place_id == Place.id)
            .where(
                Place.category_id.in_(role_ids),
                Place.status == "approved",
                Place.lat.between(min(a.lat, b.lat) - pad_lat, max(a.lat, b.lat) + pad_lat),
                Place.lng.between(min(a.lng, b.lng) - pad_lng, max(a.lng, b.lng) + pad_lng),
                or_(popularity >= MIN_POPULARITY, listed),
            )
            .options(selectinload(Place.category))
            .order_by(popularity.desc())
            .limit(SCAN_CAP)
        )
        return [(p, float(pop), bool(cur)) for p, pop, cur in (await self._s.execute(stmt)).all()]

    async def _ranks(self, place_ids: list[int]) -> dict[int, dict[str, Any]]:
        rows = await self._s.execute(
            select(PlaceSource.place_id, PlaceSource.raw).where(
                PlaceSource.place_id.in_(place_ids), PlaceSource.provider == "tmap_hub"
            )
        )
        return {pid: raw if isinstance(raw, dict) else json.loads(raw or "{}") for pid, raw in rows}

    def _item(self, p: Place, extra_m: float, rank: dict[str, Any] | None, curated: bool) -> AlongItem:
        minutes = detour_minutes(extra_m)
        signal = visited_signal(rank or {})
        if signal is None and curated:
            signal = Signal(kind="designated", label="관광공사 소개", source="한국관광공사 관광정보")
        return AlongItem(
            place=PlaceBrief(
                id=p.public_id,
                name=get_tag_rules().sign_name(p.name),
                category=p.category.code,
                category_name=p.category.name,
                lat=p.lat,
                lng=p.lng,
                address=p.road_address or p.address,
                thumbnail_url=p.thumbnail_url,
                price_per_person=None if p.is_free else p.price_per_person,
                price_is_estimated=p.price_is_estimated,
                is_free=p.is_free,
            ),
            detour_min=minutes,
            line=" · ".join(x for x in (f"가는 길에 {minutes}분 더", signal.label if signal else None) if x),
            source=signal.source if signal else None,
        )
