from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.course import PlaceBrief


class PlaceSearchItem(PlaceBrief):
    role: str
    distance_m: int | None = None


class PlaceSearchResponse(BaseModel):
    items: list[PlaceSearchItem]
    next_cursor: str | None = None
    engine: str = Field(description="opensearch | sql")


class AutocompleteItem(BaseModel):
    id: str
    name: str
    category: str


class AutocompleteResponse(BaseModel):
    items: list[AutocompleteItem]


class MenuOut(BaseModel):
    name: str
    price: int
    is_signature: bool


class OpeningHourOut(BaseModel):
    dow: int = Field(description="0=월 … 6=일")
    open: str | None = None
    close: str | None = None
    break_start: str | None = None
    break_end: str | None = None
    is_closed: bool = False


class CongestionHour(BaseModel):
    hour: int
    value: float


class ReviewSummary(BaseModel):
    rating: float | None
    review_count: int
    bayes_rating: float | None
    sentiment_score: float | None
    sentiment_count: int
    aspects: dict[str, float]


class PlaceDetail(PlaceBrief):
    role: str
    region: str | None = None
    phone: str | None = None
    description: str | None = None
    images: list[str] = Field(default_factory=list)
    menus: list[MenuOut] = Field(default_factory=list)
    opening_hours: list[OpeningHourOut] = Field(default_factory=list)
    congestion_today: list[CongestionHour] = Field(default_factory=list)
    reviews: ReviewSummary


class AttractionItem(BaseModel):
    id: str
    kind: str = Field(description="place | event")
    type: str = Field(description="park | exhibition | festival | culture | attraction")
    name: str
    category: str
    lat: float
    lng: float
    address: str | None = None
    is_free: bool
    price: int | None = None
    price_is_estimated: bool = False
    starts_on: date | None = None
    ends_on: date | None = None
    rating: float | None = None
    thumbnail_url: str | None = Field(default=None, description="그 장소의 실제 사진(있을 때만)")


class AttractionList(BaseModel):
    items: list[AttractionItem]
    next_cursor: str | None = Field(default=None, description="다음 페이지가 있으면 그 시작 위치")


class EventOut(BaseModel):
    id: str
    title: str
    category: str | None = None
    description: str | None = None
    address: str | None = None
    lat: float
    lng: float
    starts_on: date
    ends_on: date
    is_free: bool
    price: int | None = None
    booking_url: str | None = None
    thumbnail_url: str | None = None


class EventList(BaseModel):
    items: list[EventOut]


class PlaceSuggestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str
    name: str = Field(min_length=1, max_length=100)
    category: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=200)
    price_per_person: int | None = Field(default=None, ge=0)
    is_free: bool = False
    note: str | None = Field(default=None, max_length=500)


class PlaceSuggestResponse(BaseModel):
    id: str
    status: str
