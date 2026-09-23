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


class UniversityOut(BaseModel):
    """docs/34: a campus that can anchor a day (전국대학및전문대학정보표준데이터 + our own place data)."""

    id: str = Field(description="요청의 anchor.id 로 보낸다")
    name: str
    address: str | None = None
    lat: float
    lng: float


class UniversityList(BaseModel):
    items: list[UniversityOut]


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
    performances: bool = Field(default=False, description="공연 조회 가능 여부 (KOPIS 키가 있을 때만 true)")


class LocalSpecialty(BaseModel):
    word: str
    count: int = Field(description="이 동네에서 간판에 이 말이 들어간 가게 수")
    lift: float = Field(description="전국 평균 대비 몇 배나 몰려 있는지")


class LocalSight(BaseModel):
    name: str
    mentions: int = Field(default=0, description="주변 가게가 이 이름을 간판에 빌려 쓴 횟수")
    # 코스 지도 위에 띄우고 장소 상세를 열 수 있게 (지도 앱으로 내보내지 않는다). 장소가 사라졌으면 None
    id: str | None = Field(default=None, description="장소 public id (GET /places/{id})")
    lat: float | None = None
    lng: float | None = None


class HotPlace(BaseModel):
    id: str
    name: str
    category: str
    category_name: str | None = None
    rank: int = Field(description="그 시군구에서 사람들이 찾아간 순위 (티맵 내비게이션 실측, 1이 가장 많이)")
    lat: float
    lng: float
    address: str | None = None
    thumbnail_url: str | None = None
    is_free: bool = False


class HotPlaces(BaseModel):
    """그 지역에서 사람들이 실제로 많이 가는 곳. 리뷰나 별점이 아니라 내비게이션 실측 순위다."""

    region: str
    scope: str = Field(description="순위를 읽은 범위의 이름: 그 동네에 자료가 적으면 그 동네가 속한 시군구")
    source: str = "한국관광공사 · 티맵모빌리티 (내비게이션 목적지 실측)"
    items: list[HotPlace] = Field(default_factory=list)


class LocalSignature(BaseModel):
    """이 동네가 무엇으로 알려져 있는지. 사람이 적은 글이 아니라 장소 이름에서 계산한 값이다."""

    region: str
    shops: int = 0
    specialties: list[LocalSpecialty] = Field(default_factory=list)
    sights: list[LocalSight] = Field(default_factory=list)
