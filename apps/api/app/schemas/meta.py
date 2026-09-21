from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import LatLng


class RegionParent(BaseModel):
    slug: str
    name: str


class RegionOut(BaseModel):
    slug: str
    name: str
    level: int
    center: LatLng
    radius_m: int
    parent: RegionParent | None = None
    place_count: int = 0


class RegionList(BaseModel):
    items: list[RegionOut]


class BudgetRange(BaseModel):
    min: int | None = None
    max: int | None = None


class PerPersonBudget(BudgetRange):
    typical: int | None = None


class PurposeOut(BaseModel):
    code: str
    name: str
    icon: str | None = None
    description: str | None = None
    recommended_budget: BudgetRange = Field(description="기준 인원(default_party_size) 전체의 총액")
    budget_per_person: PerPersonBudget = Field(description="1인당 범위. typical 은 '적당히'의 기준(기하평균)")
    default_party_size: int = 2
    max_party_size: int | None = None
    time_bands: list[str] = Field(default_factory=list)
    min_budget_per_person: int | None = None


class PurposeList(BaseModel):
    items: list[PurposeOut]


class CategoryOut(BaseModel):
    code: str
    name: str
    course_role: str
    default_stay_min: int
    children: list[CategoryOut] = Field(default_factory=list)


class CategoryList(BaseModel):
    items: list[CategoryOut]


class TagOut(BaseModel):
    name: str
    group: str


class TagList(BaseModel):
    items: list[TagOut]


class BannerOut(BaseModel):
    id: int
    title: str
    image_url: str
    link_url: str | None = None
    placement: str
    priority: int


class BannerList(BaseModel):
    items: list[BannerOut]


class Features(BaseModel):
    """What this deployment can actually do — the web hides entry points it cannot honour."""

    chat: bool = Field(description="챗봇 사용 가능 여부 (LLM 제공자가 설정돼 있을 때만 true)")


class LocalSpecialty(BaseModel):
    word: str
    count: int = Field(description="이 동네에서 간판에 이 말이 들어간 가게 수")
    lift: float = Field(description="전국 평균 대비 몇 배나 몰려 있는지")


class LocalSight(BaseModel):
    name: str
    mentions: int = Field(default=0, description="주변 가게가 이 이름을 간판에 빌려 쓴 횟수")


class LocalSignature(BaseModel):
    """이 동네가 무엇으로 알려져 있는지. 사람이 적은 글이 아니라 장소 이름에서 계산한 값이다."""

    region: str
    shops: int = 0
    specialties: list[LocalSpecialty] = Field(default_factory=list)
    sights: list[LocalSight] = Field(default_factory=list)
