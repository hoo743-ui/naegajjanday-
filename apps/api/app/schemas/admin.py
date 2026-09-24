from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models import FEATURE_KEYS


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- places -------------------------------------------------------------------------------------

PlaceStatus = Literal["pending", "approved", "rejected", "hidden", "closed"]


class AdminPlaceOut(BaseModel):
    id: str
    name: str
    region: str
    category: str
    status: str
    lat: float
    lng: float
    address: str | None = None
    price_per_person: int | None = None
    is_free: bool
    data_quality: float
    sources: list[str] = Field(default_factory=list)
    tags: dict[str, float] = Field(
        default_factory=dict, description="tag name → weight (same shape as the PATCH body)"
    )
    created_at: datetime


class AdminPlaceList(BaseModel):
    items: list[AdminPlaceOut]
    next_cursor: str | None = None


class AdminPlaceCreate(Strict):
    region: str
    category: str
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = None
    phone: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    price_per_person: int | None = Field(default=None, ge=0)
    is_free: bool = False
    tags: dict[str, float] = Field(default_factory=dict)


class AdminPlacePatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = None
    phone: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    price_per_person: int | None = Field(default=None, ge=0)
    is_free: bool | None = None
    status: PlaceStatus | None = None
    tags: dict[str, float] | None = None


class ModerationNote(Strict):
    note: str | None = Field(default=None, max_length=500)


class BulkApproveRequest(Strict):
    ids: list[str] = Field(min_length=1, max_length=500)


class BulkResult(BaseModel):
    updated: int
    not_found: list[str] = Field(default_factory=list)


class MergeRequest(Strict):
    duplicate_id: str = Field(description="이 장소가 {id} 로 흡수되고 hidden 처리된다")
    note: str | None = None


class RevisionOut(BaseModel):
    id: int
    action: str
    admin_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    note: str | None
    created_at: datetime


class RevisionList(BaseModel):
    items: list[RevisionOut]


# --- events / banners ---------------------------------------------------------------------------


class EventIn(Strict):
    region: str
    title: str = Field(min_length=1, max_length=200)
    category: str | None = None
    description: str | None = None
    address: str | None = None
    # docs/34: a university festival — the campus id (GET /meta/universities). Without lat/lng the event
    # stands at the campus.
    university: str | None = Field(default=None, max_length=64)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    starts_on: date
    ends_on: date
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    priority: int = Field(default=0, ge=0, le=100)
    price: int | None = Field(default=None, ge=0)
    is_free: bool = False
    booking_url: str | None = None
    status: Literal["pending", "approved", "ended"] = "approved"

    @model_validator(mode="after")
    def _period(self) -> EventIn:
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on 은 starts_on 이후여야 해요")
        return self


class EventPatch(Strict):
    title: str | None = None
    description: str | None = None
    address: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    start_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    priority: int | None = Field(default=None, ge=0, le=100)
    price: int | None = Field(default=None, ge=0)
    is_free: bool | None = None
    booking_url: str | None = None
    status: Literal["pending", "approved", "ended"] | None = None


class AdminEventOut(BaseModel):
    id: str
    region: str
    title: str
    category: str | None
    description: str | None = None
    address: str | None = None
    lat: float
    lng: float
    starts_on: date
    ends_on: date
    start_time: str | None = None
    end_time: str | None = None
    priority: int = 0
    university: str | None = Field(default=None, description="이 행사가 속한 캠퍼스 id (docs/34)")
    university_name: str | None = None
    is_free: bool
    price: int | None
    booking_url: str | None = None
    status: str
    provider: str


class AdminEventList(BaseModel):
    items: list[AdminEventOut]


class BannerIn(Strict):
    title: str = Field(min_length=1, max_length=100)
    image_url: str
    link_url: str | None = None
    placement: str = "home"
    region: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int = 0
    is_active: bool = True


class BannerPatch(Strict):
    title: str | None = None
    image_url: str | None = None
    link_url: str | None = None
    placement: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int | None = None
    is_active: bool | None = None


class AdminBannerOut(BaseModel):
    id: int
    title: str
    image_url: str
    link_url: str | None
    placement: str
    region: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    priority: int
    is_active: bool


class AdminBannerList(BaseModel):
    items: list[AdminBannerOut]


class PresignRequest(Strict):
    filename: str
    content_type: str


# --- regions ------------------------------------------------------------------------------------

RegionStatus = Literal["draft", "collecting", "active", "paused"]


class RegionIn(Strict):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=60)
    name: str = Field(min_length=1, max_length=60)
    level: int = Field(ge=1, le=3)
    parent: str | None = None
    center_lat: float = Field(ge=-90, le=90)
    center_lng: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=1200, ge=100, le=50000)
    area_code: str | None = None
    status: RegionStatus = "draft"
    search_keywords: list[str] = Field(default_factory=list)


class RegionPatch(Strict):
    name: str | None = None
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lng: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int | None = Field(default=None, ge=100, le=50000)
    area_code: str | None = None
    status: RegionStatus | None = None
    search_keywords: list[str] | None = None


class AdminRegionOut(BaseModel):
    slug: str
    name: str
    level: int
    parent: str | None
    center_lat: float
    center_lng: float
    radius_m: int
    area_code: str | None
    status: str
    search_keywords: list[str]
    place_counts: dict[str, int] = Field(default_factory=dict)


class AdminRegionList(BaseModel):
    items: list[AdminRegionOut]


class CollectRequest(Strict):
    providers: list[str] = Field(min_length=1)
    job_type: Literal["full", "incremental"] = "full"


# --- scoring / templates ------------------------------------------------------------------------


class ScoringProfileBody(Strict):
    weights: dict[str, float]
    params: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    experiment_key: str | None = None

    @model_validator(mode="after")
    def _weights(self) -> ScoringProfileBody:
        unknown = set(self.weights) - set(FEATURE_KEYS)
        if unknown:
            raise ValueError(f"알 수 없는 피처: {sorted(unknown)}")
        if any(v < 0 for v in self.weights.values()):
            raise ValueError("가중치는 0 이상이어야 해요")
        if abs(sum(self.weights.values()) - 1.0) > 0.001:
            raise ValueError("가중치 합은 1 이어야 해요")
        return self


class ScoringProfileOut(BaseModel):
    purpose: str
    version: int
    weights: dict[str, float]
    params: dict[str, Any]
    is_active: bool
    experiment_key: str | None


class SlotBody(Strict):
    course_role: str
    budget_share: float = Field(ge=0, le=1)
    is_optional: bool = False
    is_order_flexible: bool = False
    earliest_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    latest_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    min_slot_budget: int | None = Field(default=None, ge=0)


class TemplateIn(Strict):
    code: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    purpose: str
    name: str
    time_band: Literal["lunch", "afternoon", "evening", "night", "fullday"]
    min_budget_per_person: int = Field(ge=0)
    party_min: int = Field(default=1, ge=1)
    party_max: int = Field(default=8, ge=1)
    is_active: bool = True
    slots: list[SlotBody] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _shares(self) -> TemplateIn:
        if abs(sum(s.budget_share for s in self.slots) - 1.0) > 0.01:
            raise ValueError("슬롯 budget_share 합은 1 이어야 해요")
        if self.party_max < self.party_min:
            raise ValueError("party_max 는 party_min 이상이어야 해요")
        return self


class TemplatePatch(Strict):
    name: str | None = None
    min_budget_per_person: int | None = Field(default=None, ge=0)
    party_min: int | None = Field(default=None, ge=1)
    party_max: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    slots: list[SlotBody] | None = Field(default=None, min_length=1, max_length=8)


class TemplateOut(BaseModel):
    code: str
    purpose: str
    name: str
    time_band: str
    min_budget_per_person: int
    party_min: int
    party_max: int
    is_active: bool
    slots: list[SlotBody]


class TemplateList(BaseModel):
    items: list[TemplateOut]


class TagAffinitiesBody(Strict):
    affinities: dict[str, float]

    @model_validator(mode="after")
    def _range(self) -> TagAffinitiesBody:
        if any(not -1 <= v <= 1 for v in self.affinities.values()):
            raise ValueError("affinity 는 -1 ~ 1 사이여야 해요")
        return self


# --- ingestion ----------------------------------------------------------------------------------


class IngestionJobIn(Strict):
    provider: str
    region: str
    job_type: Literal["full", "incremental", "stats", "sentiment"] = "full"


class IngestionJobOut(BaseModel):
    id: int
    provider: str
    region: str | None
    job_type: str
    status: str
    fetched_count: int
    created_count: int
    updated_count: int
    failed_count: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class IngestionJobList(BaseModel):
    items: list[IngestionJobOut]
    next_cursor: str | None = None


# --- analytics / system -------------------------------------------------------------------------


class HeatCell(BaseModel):
    region: str
    purpose: str
    count: int


class RecommendationStats(BaseModel):
    date_from: date
    date_to: date
    generated: int
    saved: int
    save_rate: float
    reroll_rate: float = Field(description="같은 사용자/입력으로 10분 내 재요청한 비율")
    avg_budget_total: float | None
    avg_budget_per_person: float | None
    slot_empty_rate: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    heatmap: list[HeatCell]


class TopPlace(BaseModel):
    id: str
    name: str
    region: str
    category: str
    recommend_count: int
    save_count: int


class TopPlaceList(BaseModel):
    items: list[TopPlace]


class CacheInvalidateRequest(Strict):
    prefixes: list[str] = Field(
        default_factory=lambda: [
            "region:list",
            "region:one",
            "purpose:list",
            "course:",
            "cand:",
            "attractions:",
        ]
    )


class CacheInvalidateResult(BaseModel):
    deleted: int


class ReindexResult(BaseModel):
    enqueued: int
    search_backend: str
