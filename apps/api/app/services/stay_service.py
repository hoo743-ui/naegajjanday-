"""Lodging near a point, for trips longer than a day. Read-only; the rows come from the official
TourAPI lodging list (`infra/ingestion/bulk/tourapi_stay.py`) and carry no price — see `PRICE_NOTE`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import GeoPoint
from app.domain.routing.travel_time import haversine_m
from app.infra.db.models import Category, Place
from app.repositories.geo import nearest_first, within
from app.schemas import stay as dto

STAY_ROLE = "STAY"
KTO_PHOTO_HOST = "visitkorea.or.kr"
SOURCE = "한국관광공사 TourAPI (KorService2 · 숙박)"
PRICE_NOTE = (
    "숙박 요금은 공식 데이터가 없어요. 날짜·객실에 따라 달라지니 예약처에서 직접 확인해 주세요. "
    "코스 예산에는 숙박비가 들어 있지 않아요."
)
SCAN_CAP = 600  # the bbox is a square around the circle; its corners are dropped in Python below


class StayService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def near(self, lat: float, lng: float, radius_m: int, limit: int) -> dto.StayList:
        origin = GeoPoint(lat, lng)
        # category ids first: `category_id IN (…) AND status` rides ix_place_category_status_lat_lng
        stay_ids = (await self._s.scalars(select(Category.id).where(Category.course_role == STAY_ROLE))).all()
        rows: list[Place] = []
        if stay_ids:
            dialect = self._s.get_bind().dialect.name
            stmt = (
                select(Place)
                .where(Place.category_id.in_(stay_ids), Place.status == "approved")
                .where(within(Place, origin, radius_m, dialect))
                .options(selectinload(Place.category))
                .order_by(Place.thumbnail_url.is_(None), nearest_first(Place, origin))
                .limit(SCAN_CAP)
            )
            rows = list((await self._s.scalars(stmt)).all())
        measured = [(p, haversine_m(origin, GeoPoint(p.lat, p.lng))) for p in rows]
        inside = [(p, d) for p, d in measured if d <= radius_m]
        # a card with the place's own photo first, then the nearest
        inside.sort(key=lambda t: (t[0].thumbnail_url is None, t[1]))
        return dto.StayList(
            items=[_item(p, d) for p, d in inside[:limit]],
            radius_m=radius_m,
            source=SOURCE,
            has_price=False,
            price_note=PRICE_NOTE,
        )


def _item(p: Place, distance: float) -> dto.StayItem:
    return dto.StayItem(
        id=p.public_id,
        name=p.name,
        category=p.category.code,
        category_label=p.category.name,
        address=p.road_address or p.address,
        phone=p.phone,
        lat=p.lat,
        lng=p.lng,
        distance_m=round(distance),
        thumbnail_url=p.thumbnail_url,
        photo_credit=bool(p.thumbnail_url and KTO_PHOTO_HOST in p.thumbnail_url),
    )
