"""The day in pictures (2026-09-26): real photos of what the course walks past, in the order it is walked.

Founder: "코스길 주변의 사진을 결과치로 보여주면 더 각인되지 않을까?" A card shows one stop; this shows the
way — the stops that have a photo of their own and the sights beside the route between them. Only
verified photos of *that* place (place_image, docs/43) with their credit; never a mood picture, because a
mood picture of "the street" would be a picture of somewhere else.

Read-only and outside the engine, like along-the-way (docs/46): the course is not changed.
"""

from __future__ import annotations

import hashlib
import math
from itertools import pairwise

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import errors
from app.core.cache import Cache
from app.domain.image_ref import ImageRef, placeholder_kind
from app.domain.media import name_similarity
from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Category, Course, CourseStop, Place, PlaceImage
from app.infra.tagging import get_tag_rules

ROLES = ("ATTRACTION", "CULTURE", "NIGHTVIEW", "ACTIVITY")  # what a walk passes and looks at
NEAR_ROUTE_M = 200.0  # beside the way, not a detour
MAX_LEG_M = 4_000.0  # a longer hop is a ride: nothing is "on the way"
MAX_ITEMS = 8
PER_LEG = 2
SAME_NAME = 0.75
SCAN_CAP = 400
TTL_S = 600


class SceneryItem(BaseModel):
    place_id: str
    name: str
    category_name: str | None = None
    lat: float
    lng: float
    image: ImageRef = Field(description="그 장소의 실제 사진과 출처 (docs/43) — 분위기 이미지는 오지 않는다")
    is_stop: bool = Field(description="코스에 든 장소면 true, 지나가는 길의 볼거리면 false")
    position: int = Field(
        description="is_stop 이면 그 순서, 아니면 이 볼거리 앞에 들르는 장소의 순서(0=출발)"
    )
    caption: str = Field(description="'2번째 곳' · '1 → 2 가는 길에'")


class Scenery(BaseModel):
    items: list[SceneryItem]


def progress_on(a: GeoPoint, b: GeoPoint, p: GeoPoint) -> tuple[float, float]:
    """(how far along AB the point sits 0..1, how far off the segment in metres) — equirectangular."""
    k = math.cos(math.radians((a.lat + b.lat) / 2)) * 111_320.0
    ax, ay, bx, by = a.lng * k, a.lat * 111_320.0, b.lng * k, b.lat * 111_320.0
    px, py = p.lng * k, p.lat * 111_320.0
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return t, math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _leg_m(a: GeoPoint, b: GeoPoint) -> float:
    return haversine_m(a, b)


class SceneryService:
    def __init__(self, session: AsyncSession, cache: Cache) -> None:
        self._s = session
        self._cache = cache

    async def for_course(self, public_id: str) -> Scenery:
        course = (
            await self._s.execute(
                select(Course)
                .where(Course.public_id == public_id)
                .options(
                    selectinload(Course.stops).selectinload(CourseStop.place).selectinload(Place.category)
                )
            )
        ).scalar_one_or_none()
        if course is None:
            raise errors.CourseNotFound()
        stops = [s for s in sorted(course.stops, key=lambda s: s.position) if s.place is not None]
        points = [(0, GeoPoint(course.origin_lat, course.origin_lng))]
        points += [(s.position, GeoPoint(s.place.lat, s.place.lng)) for s in stops if s.place]
        state = hashlib.sha256(
            "|".join(f"{p}:{g.lat:.5f},{g.lng:.5f}" for p, g in points).encode()
        ).hexdigest()
        key = f"scenery:{public_id}:{state[:16]}"
        if (hit := await self._cache.get(key)) is not None:
            return Scenery.model_validate(hit)
        out = await self._compute(stops, points)
        await self._cache.set(key, out.model_dump(mode="json"), TTL_S)
        return out

    async def _photos(self, place_ids: list[int]) -> dict[int, PlaceImage]:
        if not place_ids:
            return {}
        rows = (
            await self._s.scalars(
                select(PlaceImage)
                .where(PlaceImage.place_id.in_(place_ids), PlaceImage.verification_status == "VERIFIED")
                .order_by(PlaceImage.relevance.desc())
            )
        ).all()
        best: dict[int, PlaceImage] = {}
        for row in rows:
            best.setdefault(row.place_id, row)
        return best

    async def _compute(self, stops: list[CourseStop], points: list[tuple[int, GeoPoint]]) -> Scenery:
        photos = await self._photos([s.place_id for s in stops if s.place_id is not None])
        seen = [s.place.name for s in stops if s.place]
        in_course = {s.place_id for s in stops}
        # (order along the day, item): a stop sits at its own position, a sight at position + progress
        ordered: list[tuple[float, SceneryItem]] = []
        for s in stops:
            if s.place is not None and (img := photos.get(s.place.id)) is not None:
                ordered.append(
                    (float(s.position), self._item(s.place, img, True, s.position, f"{s.position}번째 곳"))
                )
        role_ids = list(
            (await self._s.scalars(select(Category.id).where(Category.course_role.in_(ROLES)))).all()
        )
        used: set[int] = set()
        for (pa, a), (pb, b) in pairwise(points):
            if _leg_m(a, b) > MAX_LEG_M or _leg_m(a, b) < 100:
                continue
            near: list[tuple[float, float, Place]] = []
            for place in await self._near_leg(a, b, role_ids):
                if place.id in in_course or place.id in used:
                    continue
                t, off = progress_on(a, b, GeoPoint(place.lat, place.lng))
                if off <= NEAR_ROUTE_M and 0.0 < t < 1.0:
                    near.append((t, off, place))
            leg_photos = await self._photos([p.id for _, _, p in near])
            near = [n for n in near if n[2].id in leg_photos]
            near.sort(key=lambda n: n[1])  # right beside the way first
            picked = 0
            for t, _, place in near:
                if picked == PER_LEG:
                    break
                if any(name_similarity(place.name, n) >= SAME_NAME for n in seen):
                    continue
                seen.append(place.name)
                used.add(place.id)
                caption = f"{pa} → {pb} 가는 길에" if pa else f"{pb}번째 곳 가는 길에"
                ordered.append((pa + t, self._item(place, leg_photos[place.id], False, pa, caption)))
                picked += 1
        ordered.sort(key=lambda o: o[0])
        return Scenery(items=[item for _, item in ordered][:MAX_ITEMS])

    async def _near_leg(self, a: GeoPoint, b: GeoPoint, role_ids: list[int]) -> list[Place]:
        pad_lat = NEAR_ROUTE_M / 111_320.0
        pad_lng = pad_lat / max(0.01, math.cos(math.radians(a.lat)))
        has_photo = select(PlaceImage.place_id).where(PlaceImage.verification_status == "VERIFIED")
        stmt = (
            select(Place)
            .where(
                Place.category_id.in_(role_ids),
                Place.status == "approved",
                Place.lat.between(min(a.lat, b.lat) - pad_lat, max(a.lat, b.lat) + pad_lat),
                Place.lng.between(min(a.lng, b.lng) - pad_lng, max(a.lng, b.lng) + pad_lng),
                Place.id.in_(has_photo),
            )
            .options(selectinload(Place.category))
            .limit(SCAN_CAP)
        )
        return list((await self._s.scalars(stmt)).all())

    def _item(self, place: Place, img: PlaceImage, is_stop: bool, position: int, caption: str) -> SceneryItem:
        return SceneryItem(
            place_id=place.public_id,
            name=get_tag_rules().sign_name(place.name),
            category_name=place.category.name if place.category else None,
            lat=place.lat,
            lng=place.lng,
            image=ImageRef(
                image_type="actual",
                image_url=img.url,
                thumbnail_url=img.thumbnail_url or img.url,
                source=img.source,
                source_url=img.source_url,
                photographer=img.photographer,
                license=img.license,
                attribution_text=img.attribution_text,
                is_actual_place_photo=True,
                is_fallback_image=False,
                placeholder_kind=placeholder_kind(place.category.code if place.category else None),
            ),
            is_stop=is_stop,
            position=position,
            caption=caption,
        )
