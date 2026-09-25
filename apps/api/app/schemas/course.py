from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.domain.image_ref import ImageRef, resolve_image
from app.schemas.common import LatLng
from app.schemas.meta import LocalSignature

Transport = Literal["walk", "transit", "car"]
Algorithm = Literal["v1", "v2"]
MoveStyle = Literal["local", "balanced", "explorer"]
Pace = Literal["relaxed", "packed", "foodie", "special"]
Wish = Literal["night", "walk", "exhibition", "value", "romantic", "quiet", "indoor", "photo", "free"]
SwapStrategy = Literal["cheaper", "closer", "higher_rated", "random_top"]


class Preferences(BaseModel):
    liked_tags: list[str] = Field(default_factory=list, max_length=20)
    disliked_tags: list[str] = Field(default_factory=list, max_length=20)
    exclude_place_ids: list[str] = Field(default_factory=list, max_length=100)


class AnchorRef(BaseModel):
    """docs/34: the place a day is planned around. Only a university campus for now."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["university"] = "university"
    id: str = Field(min_length=1, max_length=64, description="캠퍼스 장소의 public id (/meta/universities)")


class CourseGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str | None = Field(default=None, examples=["seoul-hongdae"])
    regions: list[str] = Field(
        default_factory=list,
        max_length=9,
        description="하루에 여러 동네를 잇는다(방문 순서). region/origin 대신 쓰이고 예산·시간을 나눠 쓴다",
    )
    nights: int = Field(
        default=0,
        ge=0,
        le=3,
        description="몇 박. 1 이상이면 날짜별 코스(1일차 · 2일차 …)를 만든다. 숙박비는 예산에 없다",
    )
    origin: LatLng | None = None
    origin_label: str | None = Field(
        default=None,
        max_length=40,
        description="origin 의 표시 이름(역·장소). 결과 화면과 다시 짜기에 그대로 돌려준다",
    )
    anchor: AnchorRef | None = Field(
        default=None,
        description="하루의 중심(대학교). 주면 그 캠퍼스가 출발점, region/origin 은 필요 없다 (docs/34)",
    )
    purpose: str = Field(examples=["date"], description="하루의 틀을 정하는 첫 목적")
    purposes: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="함께 고른 다른 목적들. 가중치·취향은 평균, 한 목적의 금기(가족 → 술집)는 전체에 적용",
    )
    party_size: int = Field(ge=1, le=20)
    budget_total: int = Field(ge=1000, le=10_000_000, description="총 예산(원)")
    start_at: datetime | None = Field(default=None, description="생략 시 현재 시각")
    duration_min: int | None = Field(default=None, ge=60, le=960)
    style: Literal["efficient", "fun"] = Field(
        default="efficient", description="efficient=가깝고 알뜰하게 · fun=붐비는 거리·놀거리 위주"
    )
    focus: str | None = Field(
        default=None,
        max_length=12,
        description="꼭 넣을 동네 명물(signature 의 word). 생략=가장 뚜렷한 명물을 자동으로, '-'=넣지 않음",
    )
    extras: list[str] = Field(
        default_factory=list, max_length=4, description='꼭 넣을 자리. 예: ["BAR"] = 술 한잔 포함'
    )
    transport: Transport = "walk"
    include_roles: list[str] | None = None
    conditions: list[str] = Field(default_factory=list, max_length=3, description='그날의 사정. 예: ["rain"]')
    skip_roles: list[str] = Field(
        default_factory=list, max_length=6, description='코스에서 뺄 자리 (예: ["CAFE"])'
    )
    preferences: Preferences = Field(default_factory=Preferences)
    move_style: MoveStyle | None = Field(
        default=None,
        description="이동 성향. local=가까운 곳 위주 · balanced=거리와 경험의 균형(기본) · "
        "explorer=조금 멀어도 특별한 곳 (docs/29)",
    )
    algorithm: Algorithm | None = Field(
        default=None, description="추천 알고리즘 버전(비교 · 실험용). 생략 시 서버 기본값 (docs/29)"
    )
    pace: list[Pace] = Field(
        default_factory=list,
        max_length=2,
        description="어떤 하루 (docs/30): relaxed=여유롭게 · packed=알차게 · "
        "foodie=맛있는 거 중심 · special=특별한 경험",
    )
    wishes: list[Wish] = Field(
        default_factory=list,
        max_length=5,
        description="꼭 반영하고 싶은 것: night=야경 · walk=산책 · exhibition=전시 · "
        "value=가성비(더 저렴하게) · romantic=로맨틱 · quiet=조용하게(술집 · 노래방 빼고) · "
        "indoor=실내 위주(비 오는 날과 같게) · photo=사진 찍기 좋은 곳(노래방 · 오락실 빼고) · "
        "free=무료로 들를 곳 더",
    )
    scene: str | None = Field(
        default=None,
        max_length=20,
        description="누구와 (docs/48): 가족 kids · parents · adults(기본 kids), "
        "데이트 new · steady · anniversary. 목적에 없는 값은 무시한다 (GET /meta/purposes 의 scenes)",
    )
    keep_place_ids: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="다시 짤 때 그대로 둘 장소의 id(스톱의 place.id). 코스에 반드시 들어가고 "
        "exclude_place_ids 보다 우선한다. 시간 · 예산 때문에 못 넣으면 KEPT_PLACE_DROPPED 경고, "
        "모르는 id 도 같은 경고로 알리고 빼고 짠다",
    )
    alternatives: int = Field(default=2, ge=0, le=3)
    replaces: str | None = Field(
        default=None,
        max_length=40,
        description="여행의 하루를 다시 짤 때 바꿀 그 날의 코스 id. 새 코스가 같은 여행의 같은 날이 된다",
    )

    @model_validator(mode="after")
    def _region_or_origin(self) -> CourseGenerateRequest:
        if len(self.regions) >= 2:
            self.region, self.origin, self.origin_label = self.regions[0], None, None
            # a day holds three neighbourhoods at most; a trip has room for three a day
            self.regions = self.regions[: 3 * (self.nights + 1)]
        elif self.regions:
            self.region = self.region or self.regions[0]
            self.regions = []
        if self.anchor is not None:  # the campus is the centre: a region or a point would only compete
            self.region, self.regions = None, []
        elif not self.region and self.origin is None:
            raise ValueError("region, origin, anchor 중 하나는 필요해요")
        return self


class InterpretRequest(BaseModel):
    """What the wizard knows before anything is built: enough to say back how it was understood (docs/30)."""

    model_config = ConfigDict(extra="forbid")

    pace: list[Pace] = Field(default_factory=list, max_length=2)
    move_style: MoveStyle | None = None
    wishes: list[Wish] = Field(default_factory=list, max_length=5)
    liked_tags: list[str] = Field(default_factory=list, max_length=20)
    disliked_tags: list[str] = Field(default_factory=list, max_length=20)
    budget_total: int | None = Field(default=None, ge=1000, le=10_000_000)
    party_size: int = Field(default=1, ge=1, le=20)


class SummaryLine(BaseModel):
    kind: Literal["pace", "move", "wish", "detail", "budget"]
    key: str
    text: str


class InterpretResponse(BaseModel):
    summary: list[SummaryLine]
    layers: dict[str, list[str]] = Field(description="style · preference · avoid 로 나눈 해석 (화면용 아님)")


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def image(self) -> ImageRef:
        """카드에 보일 그림 한 장과 그 출처 (docs/43): 실제 사진 → 분위기 이미지 → 브랜드 그림"""
        return resolve_image(self.thumbnail_url, self.category)


class FromPrev(BaseModel):
    travel_min: int
    distance_m: int
    mode: Transport
    hop_to: str | None = Field(default=None, description="다른 동네로 넘어가는 구간이면 그 동네 이름")


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
    reason_short: str | None = Field(
        default=None,
        max_length=40,
        description="카드 부제용 한 줄(40자 이내). reason_codes 중 가장 앞선 것을 말로 옮긴 것",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="왜 여기인지 (PURPOSE_MATCH · LOCAL_SIGNIFICANCE · WORTH_THE_TRIP · UNIQUE_EXPERIENCE · "
        "USER_PREFERENCE · HIGH_PLACE_QUALITY · BUDGET_FIT · DIVERSITY · ROUTE_BALANCE)",
    )
    congestion: Congestion | None = None


class LeftoverOut(BaseModel):
    """docs/49: buffer (≤15 %, kept on purpose — prices are estimates) · spendable · underspent (≥40 %)."""

    band: Literal["buffer", "spendable", "underspent"] = "buffer"
    reason: str | None = Field(
        default=None, description="왜 남았나: USER_ASKED_VALUE · FEW_OPEN_AT_THIS_HOUR …"
    )
    text: str | None = Field(default=None, description="화면에 그대로 나가는 한 문장")


class Totals(BaseModel):
    price: int
    price_per_person: int
    budget_left: int
    budget_utilization: float
    leftover: LeftoverOut = Field(default_factory=LeftoverOut)
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
    algorithm: str = "v1"
    scoring_profile: str
    template: str | None = None
    candidates: int
    latency_ms: int


class CourseGenerateResponse(BaseModel):
    request_id: str
    courses: list[CourseOut]
    edit_key: str | None = Field(
        default=None,
        description="계정 없이 만든 코스의 편집 키. 이 브라우저만 가지고, "
        "수정 요청에 X-Course-Key 로 보낸다 (docs/28)",
    )
    nearby_events: list[NearbyEvent] = Field(default_factory=list)
    local: LocalSignature | None = None
    meta: GenerateMeta


class Suggestion(BaseModel):
    role: str
    place: PlaceBrief
    est_price: int = Field(description="일행 전체 금액")
    walk_min: int = Field(description="코스의 마지막 장소에서 걸어서")
    distance_m: int
    line: str = Field(description="화면에 그대로 나가는 한 줄")


class SuggestionList(BaseModel):
    budget_left: int
    items: list[Suggestion] = Field(default_factory=list)


class AddStopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_id: str = Field(description="suggestions 가 준 장소의 id")


class SwapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=1)
    strategy: SwapStrategy = "random_top"
    place_id: str | None = Field(
        default=None,
        max_length=64,
        description="이 장소로 바꾼다(candidates 가 준 id). 주면 strategy 는 무시한다. "
        "후보 조건을 통과하지 못하면 422 CANDIDATE_NOT_ELIGIBLE",
    )


class StopCandidate(BaseModel):
    place: PlaceBrief
    role: str
    est_price: int = Field(description="일행 전체 금액")
    price_delta: int = Field(description="지금 스톱보다 얼마 더(+) / 덜(-) 드는지, 일행 전체")
    walk_min_delta: int | None = Field(
        default=None, description="코스 전체 이동 시간이 몇 분 늘거나(+) 주는지(-). 걷는 코스가 아니면 null"
    )
    line: str = Field(max_length=40, description="화면에 그대로 나가는 짧은 이유 한 줄")


class StopCandidateList(BaseModel):
    items: list[StopCandidate] = Field(default_factory=list)


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


class AnchorEcho(BaseModel):
    kind: Literal["university"] = "university"
    id: str
    name: str
    festival: str | None = Field(default=None, description="이 코스에 들어간 그날의 행사 이름")


class CourseRequestEcho(BaseModel):
    """The conditions the course was generated with — the result page shows them next to the totals,
    and "다시 짜기" sends them back so the new course is planned around the same spot and taste."""

    region: SlugName | None = None
    origin: LatLng | None = Field(
        default=None,
        description="지역 중심이 아닌 지점(역·장소)에서 짠 코스일 때만. 다시 짤 때 그대로 보낸다",
    )
    origin_label: str | None = None
    anchor: AnchorEcho | None = Field(
        default=None, description="대학교를 중심으로 짠 코스일 때 (docs/34). 다시 짤 때 anchor 로 보낸다"
    )
    context: Literal["general_area", "specific_place", "university", "festival"] = Field(
        default="general_area",
        description="하루의 중심: 지역 · 역/장소 · 대학교 · 대학교 + 그날의 축제",
    )
    preferences: EchoPreferences = Field(default_factory=EchoPreferences)
    purpose: CodeName
    purposes: list[CodeName] = Field(default_factory=list, description="첫 목적 포함, 고른 순서대로")
    day: int | None = Field(default=None, description="여행 일정의 몇 일차인지 (1부터)")
    days: int | None = Field(default=None, description="여행 일정의 전체 일수")
    trip_budget_total: int | None = Field(
        default=None, description="여행 전체 예산 (budget_total 은 그날 몫)"
    )
    regions: list[SlugName] = Field(
        default_factory=list, description="여러 동네를 이은 코스일 때만, 방문 순서"
    )
    city: SlugName | None = Field(
        default=None, description="시 · 도 전체를 고른 여행이면 그 도시. 다시 짤 때 region 으로 보낸다"
    )
    party_size: int
    budget_total: int
    transport: Transport
    start_at: datetime
    duration_min: int | None = None
    style: str = "efficient"
    focus: str | None = None
    extras: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    # the taste picked in the wizard (docs/30): "다시 짜기" sends it back, or a reroll forgets "로맨틱하게"
    pace: list[str] = Field(default_factory=list)
    move_style: str | None = None
    wishes: list[str] = Field(default_factory=list)
    scene: str | None = None
    scene_label: str | None = Field(default=None, description="누구와의 이름: 아이와 · 기념일 …")


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
    local: LocalSignature | None = Field(default=None, description="이 동네의 명물 · 보러 오는 곳")
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
    day: int | None = Field(default=None, description="여행 일정이면 몇 일차")
    days: int | None = None
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
