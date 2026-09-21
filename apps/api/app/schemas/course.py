from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import LatLng

Transport = Literal["walk", "transit", "car"]
SwapStrategy = Literal["cheaper", "closer", "higher_rated", "random_top"]


class Preferences(BaseModel):
    liked_tags: list[str] = Field(default_factory=list, max_length=20)
    disliked_tags: list[str] = Field(default_factory=list, max_length=20)
    exclude_place_ids: list[str] = Field(default_factory=list, max_length=100)


class CourseGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = Field(default=None, examples=["seoul-hongdae"])
    origin: LatLng | None = None
    origin_label: str | None = Field(
        default=None,
        max_length=40,
        description="origin 의 표시 이름(역·장소). 결과 화면과 다시 짜기에 그대로 돌려준다",
    )
    purpose: str = Field(examples=["date"])
    party_size: int = Field(ge=1, le=20)
    budget_total: int = Field(ge=1000, le=10_000_000, description="총 예산(원)")
    start_at: datetime | None = Field(default=None, description="생략 시 현재 시각")
    duration_min: int | None = Field(default=None, ge=60, le=960)
    style: Literal["efficient", "fun"] = Field(
        default="efficient", description="efficient=가깝고 알뜰하게 · fun=붐비는 거리·놀거리 위주"
    )
    transport: Transport = "walk"
    include_roles: list[str] | None = None
    preferences: Preferences = Field(default_factory=Preferences)
    alternatives: int = Field(default=2, ge=0, le=3)

    @model_validator(mode="after")
    def _region_or_origin(self) -> CourseGenerateRequest:
        if not self.region and self.origin is None:
            raise ValueError("region 또는 origin 중 하나는 필요해요")
        return self


class PlaceBrief(BaseModel):
    id: str
    kind: Literal["place", "event"] = "place"
    name: str
    category: str
    category_name: str | None = None  # human label ("고기·구이") — the UI must never show the raw code
    lat: float
    lng: float
    address: str | None = None
    thumbnail_url: str | None = None
    rating: float | None = None
    review_count: int = 0
    price_per_person: int | None = None
    price_is_estimated: bool = False  # true → show as "예상" (category prior, not a menu price)
    is_free: bool = False
    tags: list[str] = Field(default_factory=list)


class FromPrev(BaseModel):
    travel_min: int
    distance_m: int
    mode: Transport


class Congestion(BaseModel):
    level: str
    value: float


class StopOut(BaseModel):
    position: int
    role: str
    place: PlaceBrief
    arrive_at: datetime
    leave_at: datetime
    est_price: int
    from_prev: FromPrev
    score: float
    score_breakdown: dict[str, float]
    reason: str | None = None
    congestion: Congestion | None = None


class Totals(BaseModel):
    price: int
    price_per_person: int
    budget_left: int
    budget_utilization: float
    travel_min: int
    distance_m: int
    duration_min: int
    score: float


class RouteOut(BaseModel):
    polyline: str
    optimizer: str | None = None


class Warning(BaseModel):
    code: str
    detail: str | None = None
    meta: dict[str, Any] | None = None


class CourseOut(BaseModel):
    id: str
    label: str
    status: str = "generated"
    summary: str | None = None
    tip: str | None = None
    totals: Totals
    stops: list[StopOut]
    route: RouteOut
    warnings: list[Warning] = Field(default_factory=list)


class NearbyEvent(BaseModel):
    id: str
    title: str
    starts_on: date
    ends_on: date
    distance_m: int
    is_free: bool


class GenerateMeta(BaseModel):
    engine_version: str
    scoring_profile: str
    template: str | None = None
    candidates: int
    latency_ms: int


class CourseGenerateResponse(BaseModel):
    request_id: str
    courses: list[CourseOut]
    nearby_events: list[NearbyEvent] = Field(default_factory=list)
    meta: GenerateMeta


class SwapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=1)
    strategy: SwapStrategy = "random_top"


class ReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[int] = Field(min_length=1, description="현재 position 값들을 새 순서대로 나열")


class StopFeedback(BaseModel):
    position: int
    liked: bool


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=1, le=5)
    visited: bool = False
    actual_spend: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=1000)
    stop_feedback: list[StopFeedback] = Field(default_factory=list)


class OgMeta(BaseModel):
    title: str
    description: str
    url: str
    image: str | None = None


class CodeName(BaseModel):
    code: str
    name: str


class SlugName(BaseModel):
    slug: str
    name: str


class EchoPreferences(BaseModel):
    liked_tags: list[str] = Field(default_factory=list)
    disliked_tags: list[str] = Field(default_factory=list)


class CourseRequestEcho(BaseModel):
    """The conditions the course was generated with — the result page shows them next to the totals,
    and "다시 짜기" sends them back so the new course is planned around the same spot and taste."""

    region: SlugName | None = None
    origin: LatLng | None = Field(
        default=None,
        description="지역 중심이 아닌 지점(역·장소)에서 짠 코스일 때만. 다시 짤 때 그대로 보낸다",
    )
    origin_label: str | None = None
    preferences: EchoPreferences = Field(default_factory=EchoPreferences)
    purpose: CodeName
    party_size: int
    budget_total: int
    transport: Transport
    start_at: datetime
    duration_min: int | None = None
    style: str = "efficient"


class SiblingRef(BaseModel):
    id: str
    label: str


class CourseDetailResponse(BaseModel):
    course: CourseOut
    og: OgMeta
    request: CourseRequestEcho
    siblings: list[SiblingRef] = Field(
        default_factory=list, description="같은 요청에서 나온 코스들 (자기 자신 포함, 탭 순서)"
    )
    nearby_events: list[NearbyEvent] = Field(default_factory=list)
    # viewer context: a shared link is opened by people who do not own the course
    is_owner: bool = Field(default=False, description="로그인한 조회자가 이 코스의 주인인지")
    can_edit: bool = Field(
        default=True, description="swap / reorder / save 가 403 없이 되는지 (주인 없는 코스는 누구나 가능)"
    )
    is_saved: bool = Field(
        default=False, description="조회자 본인이 저장한 코스인지 (남의 저장 코스는 false)"
    )


class CourseListItem(BaseModel):
    id: str
    label: str
    summary: str | None
    status: str
    total_price: int
    party_size: int
    created_at: datetime
    duration_min: int = 0
    region_name: str | None = None
    purpose_name: str | None = None
    stop_names: list[str] = Field(default_factory=list, description="방문 순서대로의 장소 이름")


class CourseListResponse(BaseModel):
    items: list[CourseListItem]
    next_cursor: str | None = None
