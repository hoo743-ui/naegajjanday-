from __future__ import annotations

from pydantic import BaseModel, Field


class StayItem(BaseModel):
    id: str = Field(description="place.public_id")
    name: str
    category: str = Field(description="category code, e.g. stay.hotel")
    category_label: str = Field(description="카테고리 한글 이름")
    address: str | None = None
    phone: str | None = None
    lat: float
    lng: float
    distance_m: int = Field(description="기준 좌표에서의 직선거리")
    thumbnail_url: str | None = Field(default=None, description="그 숙소의 실제 사진. 없으면 null")
    photo_credit: bool = Field(description="true 면 한국관광공사 사진 — 화면에 출처를 표기해야 한다")


class StayList(BaseModel):
    items: list[StayItem]
    radius_m: int
    source: str = Field(description="데이터 출처")
    has_price: bool = Field(default=False, description="공식 요금 데이터가 있는지. 지금은 항상 false")
    price_note: str = Field(description="요금에 대한 안내 문구")
