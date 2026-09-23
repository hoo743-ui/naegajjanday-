/**
 * API 타입 — docs/03-api-spec.md 를 손으로 옮긴 것.
 *
 * 정본은 FastAPI가 내보내는 OpenAPI(`/v1/openapi.json`)다. 백엔드가 떠 있으면
 *   npm run gen:api
 * 로 `schema.gen.ts` 를 생성(openapi-typescript)하고, 이 파일의 타입을
 * `components["schemas"][...]` 별칭으로 점진 교체한다. 그 전까지는 이 파일이 계약이다.
 */

// ── 공통 ────────────────────────────────────────────────────
export interface LatLng {
  lat: number;
  lng: number;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface ItemList<T> {
  items: T[];
}

/** RFC 9457 Problem Details + 서비스 확장 필드 */
export interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  code: string;
  detail?: string;
  meta?: Record<string, unknown>;
  trace_id?: string;
}

export type KnownErrorCode =
  | "BUDGET_TOO_LOW"
  | "REGION_NOT_FOUND"
  | "REGION_NOT_READY"
  | "SLOT_EMPTY"
  | "NO_COURSE_AVAILABLE"
  | "PURPOSE_NOT_FOUND"
  | "SWAP_NOT_POSSIBLE"
  | "LLM_UNAVAILABLE"
  | "COURSE_NOT_FOUND"
  | "NOT_FOUND"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "RATE_LIMITED"
  | "VALIDATION_ERROR"
  | "INTERNAL_ERROR"
  // 클라이언트에서 합성하는 코드
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "UNKNOWN";

export type ErrorCode = KnownErrorCode | (string & {});

// ── 메타 ────────────────────────────────────────────────────
export interface Region {
  slug: string;
  name: string;
  level: number;
  center: LatLng;
  radius_m: number;
  parent: { slug: string; name: string } | null;
  place_count: number;
}

/** 그 지역에서 사람들이 실제로 많이 가는 곳 한 곳 (내비게이션 목적지 실측 순위) */
export interface HotPlace {
  id: string;
  name: string;
  category: string;
  category_name: string | null;
  /** 그 시군구에서 몇 번째로 많이 찾아갔는지 (1이 가장 많이) */
  rank: number;
  lat: number;
  lng: number;
  address: string | null;
  thumbnail_url: string | null;
  is_free: boolean;
}

/** GET /meta/regions/{slug}/hot */
export interface HotPlaces {
  region: string;
  /** 순위를 읽은 범위: 동네에 자료가 적으면 그 동네가 속한 시군구 */
  scope: string;
  source: string;
  items: HotPlace[];
}

/** GET /meta/features — 이 환경에서 실제로 되는 기능. 안 되는 기능의 입구는 미리 접는다. */
export interface Features {
  /** LLM 제공자가 설정돼 있을 때만 true */
  chat: boolean;
  /** 공연 정보(KOPIS) 키가 설정돼 있을 때만 true */
  performances?: boolean;
}

/** 장소 상세 (GET /places/{id}): 조사된 메뉴 · 사진 · 전화 · 영업시간 · 개업 연도 · 공적 표식 */
export interface PlaceDetail extends PlaceSummary {
  phone: string | null;
  description: string | null;
  images: string[];
  menus: { name: string; price: number; is_signature: boolean }[];
  opening_hours: { dow: number; open: string | null; close: string | null; is_closed: boolean }[];
  /** 영업 신고(인허가) 연도 */
  since_year: number | null;
  /** 인허가상의 업태 (호프/통닭 · 한식 · 까페 …) */
  licensed_as: string | null;
  marks: { tag: string; by: string }[];
}

/** 관광공사에 등재된 숙소. 요금은 공식 데이터가 없어 주지 않는다 */
export interface Stay {
  id: string;
  name: string;
  category: string;
  category_label: string;
  address: string | null;
  lat: number;
  lng: number;
  distance_m: number;
  thumbnail_url: string | null;
  photo_credit: boolean;
}

export interface StayList {
  items: Stay[];
  radius_m: number;
  source: string;
  has_price: boolean;
  price_note: string;
}

/** 고른 시간대에 실제로 하는 공연 (KOPIS) */
export interface Performance {
  id: string;
  title: string;
  genre: string | null;
  venue: { name: string; address: string | null; lat: number; lng: number; distance_m: number };
  period_from: string;
  period_to: string;
  show_times: string[];
  runtime_min: number | null;
  price_text: string | null;
  poster_url: string | null;
  detail_url: string | null;
}

export interface PerformanceList {
  items: Performance[];
  available: boolean;
  reason: string | null;
  partial: boolean;
  attribution: string;
}

export interface Purpose {
  code: string;
  name: string;
  /** 이모지 또는 아이콘 키. 표시용일 뿐, 로직에 쓰지 않는다. */
  icon: string;
  description?: string;
  /** 1인 기준 추천 예산 범위(원) */
  budget_range: { min: number; max: number; typical?: number };
  default_party_size?: number;
  max_party_size?: number;
}

export interface Category {
  code: string;
  name: string;
  course_role: CourseRole | null;
  children?: Category[];
}

export interface Tag {
  code: string;
  name: string;
  group: string;
  group_name?: string;
}

export interface Banner {
  id: string;
  title: string;
  subtitle?: string;
  image_url: string | null;
  link_url: string;
  placement: string;
}

// ── 코스 ────────────────────────────────────────────────────
export type CourseRole =
  | "MEAL"
  | "CAFE"
  | "DESSERT"
  | "ATTRACTION"
  | "CULTURE"
  | "ACTIVITY"
  | "BAR"
  | "NIGHTVIEW"
  | (string & {});

export type Transport = "walk" | "transit" | "car";
export type SwapStrategy = "cheaper" | "closer" | "higher_rated" | "random_top";

/** 이 동네가 무엇으로 알려져 있는지. 사람이 쓴 글이 아니라 간판 통계에서 계산한 값이다 (API: domain/signature) */
export interface LocalSignature {
  region: string;
  shops: number;
  /** count = 이 동네에서 간판에 그 말이 들어간 가게 수, lift = 전국 평균 대비 몇 배 */
  specialties: { word: string; count: number; lift: number }[];
  /** id · lat · lng: 코스 지도에 띄우고 장소 상세를 연다. 예전 코스(또는 장소가 사라진 경우)에는 없다 */
  sights: { name: string; mentions: number; id?: string | null; lat?: number | null; lng?: number | null }[];
}

/** focus 값: 동네 명물을 코스에 넣지 않는다 */
export const FOCUS_OFF = "-";

export interface GenerateCourseRequest {
  region?: string;
  origin?: LatLng;
  /** origin 의 표시 이름(역·장소). 결과 화면 머리말과 "다시 짜기"에 그대로 돌아온다 */
  origin_label?: string;
  /** docs/34: 하루의 중심(대학교). 주면 region/origin 은 보내지 않는다 */
  anchor?: { kind: "university"; id: string };
  purpose: string;
  party_size: number;
  budget_total: number;
  start_at?: string;
  duration_min?: number;
  /** efficient = 가깝고 알뜰하게(기본) · fun = 붐비는 거리·놀거리 위주 */
  style?: CourseStyle;
  /** 꼭 넣을 자리. ["BAR"] = 술 한잔 포함 */
  extras?: string[];
  /** 그날의 사정. ["rain"] = 비 오는 날(실내 위주) */
  conditions?: string[];
  /** 함께 고른 다른 목적들. 가중치·취향은 평균, 한 목적의 금기(가족 → 술집)는 전체에 적용 */
  purposes?: string[];
  /** 하루에 여러 동네를 잇는다(방문 순서, 최대 3). 주면 region 대신 쓰인다 */
  regions?: string[];
  /** 몇 박. 1 이상이면 날짜별 코스(1일차 · 2일차 …)가 온다. 숙박비는 예산 밖 */
  nights?: number;
  /** 꼭 넣을 동네 명물. 생략 = 가장 뚜렷한 명물을 자동으로, FOCUS_OFF = 넣지 않음 */
  focus?: string;
  transport?: Transport;
  include_roles?: CourseRole[];
  preferences?: {
    liked_tags?: string[];
    disliked_tags?: string[];
    exclude_place_ids?: string[];
  };
  alternatives?: number;
  /** 여행 일정의 하루를 다시 짤 때: 바꿀 그 날의 코스 id. 새 코스가 같은 여행의 같은 날 자리에 들어간다 */
  replaces?: string;
  /** docs/30 세 질문: 어떤 하루 · 얼마나 이동 · 꼭 원하는 것 (해석은 API 가 한다) */
  pace?: ("relaxed" | "packed" | "foodie" | "special")[];
  move_style?: MoveStyle;
  wishes?: ("night" | "walk" | "exhibition" | "value" | "romantic")[];
}

export type CourseStyle = "efficient" | "fun";

export const SCORE_FEATURES = [
  "budget",
  "distance",
  "rating",
  "sentiment",
  "congestion",
  "time_fit",
  "preference",
  "purpose_fit",
  "curated",
  "buzz",
] as const;
export type ScoreFeature = (typeof SCORE_FEATURES)[number];
export type ScoreBreakdown = Record<ScoreFeature, number>;

export interface PlaceSummary {
  id: string;
  name: string;
  category: string;
  category_name?: string;
  lat: number;
  lng: number;
  address: string;
  thumbnail_url: string | null;
  rating: number | null;
  review_count: number;
  /** 무료이거나 가격을 모르면 null */
  price_per_person: number | null;
  /** true 면 메뉴 가격이 아니라 업종·지역 평균으로 추정한 값 → 화면에 "예상" 표시 */
  price_is_estimated?: boolean;
  is_free?: boolean;
  tags: string[];
  /** event = 기간이 있는 행사(장소 상세가 없다) */
  kind?: "place" | "event";
}

export interface TravelLeg {
  travel_min: number;
  distance_m: number;
  mode: Transport;
  /** 다른 동네로 넘어가는 구간이면 그 동네 이름 (여러 동네를 이은 코스) */
  hop_to?: string | null;
}

export interface Congestion {
  level: string;
  value: number;
}

export interface Stop {
  position: number;
  role: CourseRole;
  place: PlaceSummary;
  arrive_at: string;
  leave_at: string;
  est_price: number;
  from_prev: TravelLeg | null;
  score: number;
  score_breakdown: ScoreBreakdown;
  reason: string | null;
  /** 왜 이 장소인지 (docs/29 §15). 예전 코스에는 없다 */
  reason_codes?: ReasonCode[];
  congestion: Congestion | null;
}

export type ReasonCode =
  | "PURPOSE_MATCH"
  | "LOCAL_SIGNIFICANCE"
  | "WORTH_THE_TRIP"
  | "UNIQUE_EXPERIENCE"
  | "USER_PREFERENCE"
  | "HIGH_PLACE_QUALITY"
  | "BUDGET_FIT"
  | "DIVERSITY"
  | "ROUTE_BALANCE";

/** 얼마나 이동해도 괜찮은지 (docs/29 §10): 거리를 자르는 필터가 아니라 엔진의 이동 선호 */
export type MoveStyle = "local" | "balanced" | "explorer";

export interface CourseTotals {
  price: number;
  price_per_person: number;
  budget_left: number;
  budget_utilization: number;
  travel_min: number;
  distance_m: number;
  duration_min: number;
  score: number;
}

export interface CourseWarning {
  code: string;
  /** 목 데이터는 message, 실제 API 는 detail 로 문구를 준다 */
  message?: string;
  detail?: string;
  role?: CourseRole;
}

export interface Course {
  id: string;
  label: string;
  /** generated | saved | completed */
  status?: string;
  summary: string;
  totals: CourseTotals;
  stops: Stop[];
  route: { polyline: string | null; optimizer: string };
  warnings: CourseWarning[];
}

/** 예산이 남았을 때 권하는 곳 (GET /courses/{id}/suggestions) */
export interface Suggestion {
  role: CourseRole;
  place: PlaceSummary;
  /** 일행 전체 금액 */
  est_price: number;
  /** 코스의 마지막 장소에서 걸어서 */
  walk_min: number;
  distance_m: number;
  /** 화면에 그대로 쓰는 한 줄 */
  line: string;
}

export interface SuggestionList {
  budget_left: number;
  items: Suggestion[];
}

export interface NearbyEvent {
  id: string;
  title: string;
  ends_on: string;
  distance_m: number;
  is_free: boolean;
  thumbnail_url?: string | null;
}

export interface GenerateMeta {
  engine_version: string;
  scoring_profile: string;
  candidates: number;
  latency_ms: number;
}

export interface GenerateCourseResponse {
  request_id: string;
  courses: Course[];
  /** 계정 없이 만든 코스의 편집 키 — 이 브라우저만 가진다 (lib/course-keys.ts) */
  edit_key?: string | null;
  nearby_events: NearbyEvent[];
  meta: GenerateMeta;
}

/** GET /courses/{id} — 공유 링크 조회. 생성 당시 조건과 OG 메타를 함께 준다. */
export interface CourseDetail extends Course {
  request: {
    region: { slug: string; name: string } | null;
    /** 지역 중심이 아니라 역·장소 주변으로 짠 코스일 때만 온다. 다시 짤 때 그대로 돌려보낸다 */
    origin?: LatLng | null;
    origin_label?: string | null;
    /** docs/34: 대학교를 중심으로 짠 코스. festival = 코스에 들어간 그날의 행사 */
    anchor?: { kind: "university"; id: string; name: string; festival?: string | null } | null;
    context?: "general_area" | "specific_place" | "university" | "festival";
    preferences?: { liked_tags: string[]; disliked_tags: string[] };
    purpose: { code: string; name: string };
    party_size: number;
    budget_total: number;
    transport: Transport;
    start_at: string;
    /** 사용자가 정한 만남 시간(분). 맡겼으면 null */
    duration_min?: number | null;
    style?: CourseStyle;
    /** 이 코스가 실제로 중심에 둔 동네 명물 (자동으로 골랐든 사용자가 골랐든) */
    focus?: string | null;
    extras?: string[];
    conditions?: string[];
    /** 첫 목적 포함, 고른 순서대로 */
    purposes?: { code: string; name: string }[];
    /** 여러 동네를 이은 코스일 때만 */
    regions?: { slug: string; name: string }[];
    /** 여행 일정이면 몇 일차 / 전체 며칠 / 여행 전체 예산 (budget_total 은 그날 몫) */
    day?: number | null;
    days?: number | null;
    trip_budget_total?: number | null;
    /** 시 · 도 전체를 고른 여행이면 그 도시. 다시 짤 때는 첫 구역의 구가 아니라 이 도시로 요청한다 */
    city?: { slug: string; name: string } | null;
  };
  /** 같은 요청에서 나온 대안 코스들(자기 자신 포함, 탭 순서) */
  siblings: { id: string; label: string }[];
  nearby_events: NearbyEvent[];
  local?: LocalSignature | null;
  meta?: GenerateMeta;
  og: { title: string; description: string; image_url: string | null };
  /** 보는 사람 기준: 내가 저장한 코스일 때만 true (친구가 저장한 코스를 열면 false) */
  is_saved?: boolean;
  /** 보는 사람이 이 코스의 주인인지 */
  is_owner?: boolean;
  /** 바꾸기·순서 변경·저장이 되는지. 주인 없는(비로그인 생성) 코스는 누구나 true, 남의 코스는 false. 없으면 true 로 본다 */
  can_edit?: boolean;
}

export interface SwapRequest {
  position: number;
  strategy: SwapStrategy;
}

export interface ReorderRequest {
  /** 새 순서대로 나열한 기존 position 값 */
  order: number[];
}

/** 화면이 쓰는 저장 코스. API 응답(`SavedCoursePayload`)은 hooks 의 `toSavedCourse` 를 거쳐 이 모양이 된다. */
export interface SavedCourse {
  id: string;
  label: string;
  summary: string;
  saved_at: string;
  region_name: string | null;
  purpose_name: string | null;
  party_size: number;
  totals: Pick<CourseTotals, "price" | "duration_min"> & Partial<Pick<CourseTotals, "budget_left" | "travel_min">>;
  stop_names: string[];
  visited: boolean;
  /** 여행 일정의 하루면 몇 일차 / 며칠짜리 */
  day: number | null;
  days: number | null;
}

/**
 * GET /me/courses 가 실제로 주는 항목 (API `CourseListItem`). 전부 optional 로 읽는다:
 * 옛 서버·목 핸들러(화면 모양 그대로 준다)처럼 일부만 오는 응답에도 화면이 죽지 않게 하려는 것.
 */
export interface SavedCoursePayload {
  id: string;
  label?: string | null;
  summary?: string | null;
  status?: string | null;
  total_price?: number | null;
  party_size?: number | null;
  created_at?: string | null;
  duration_min?: number | null;
  region_name?: string | null;
  purpose_name?: string | null;
  stop_names?: string[] | null;
  day?: number | null;
  days?: number | null;
  // 목 핸들러가 주는 화면 모양
  saved_at?: string | null;
  totals?: Partial<SavedCourse["totals"]> | null;
  visited?: boolean | null;
}

export interface FeedbackRequest {
  rating: number;
  visited: boolean;
  actual_spend?: number;
  stop_feedback?: { position: number; liked: boolean }[];
}

// ── 탐색 ────────────────────────────────────────────────────
export type AttractionType = "attraction" | "park" | "exhibition" | "festival" | "culture";

export interface Attraction {
  id: string;
  type: AttractionType;
  name: string;
  /** 업종 코드(예: attraction.park). 대표 사진을 고를 때 쓴다 */
  category?: string;
  region: { slug: string; name: string } | null;
  lat: number;
  lng: number;
  address: string;
  thumbnail_url: string | null;
  is_free: boolean;
  price_per_person: number;
  /** 축제·전시처럼 기간이 있는 경우 */
  period: { starts_on: string; ends_on: string } | null;
  tags: string[];
  summary: string;
  rating: number | null;
}

export interface EventItem {
  id: string;
  title: string;
  type: "festival" | "exhibition" | "performance" | "market" | (string & {});
  region: { slug: string; name: string } | null;
  venue: string;
  starts_on: string;
  ends_on: string;
  is_free: boolean;
  price: number | null;
  thumbnail_url: string | null;
  link_url: string | null;
}

// ── 사용자 ──────────────────────────────────────────────────
export type Role = "user" | "operator" | "admin";
export type OAuthProvider = "kakao" | "naver" | "google";

/** 화면이 쓰는 내 정보. API 응답(`MePayload`)은 hooks 의 `toMe` 를 거친다 → nickname 은 항상 채워져 있다. */
export interface Me {
  id: string;
  nickname: string;
  email: string | null;
  avatar_url: string | null;
  role: Role;
  /** 연결된 소셜 계정이 없으면(운영자가 만든 계정 등) null → 화면은 "○○ 로그인" 줄을 숨긴다 */
  provider: OAuthProvider | null;
  created_at: string;
}

/** GET·PATCH /me 가 실제로 주는 모양 (API `UserOut`): nickname 은 null 일 수 있고 avatar_url 은 없다 */
export interface MePayload {
  id: string;
  nickname?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  role: Role;
  provider?: string | null;
  status?: string;
  created_at: string;
}

/** 화면이 쓰는 취향. API 필드명은 `default_transport` 다 (`PreferencesPayload`) — hooks 가 양쪽을 맞춘다. */
export interface Preferences {
  liked_tags: string[];
  disliked_tags: string[];
  transport: Transport;
  category_weights?: Record<string, number>;
}

/** GET·PUT /me/preferences 본문 (API `PreferencesBody`, extra="forbid" → 이 네 필드 말고는 보내면 422) */
export interface PreferencesPayload {
  liked_tags?: string[] | null;
  disliked_tags?: string[] | null;
  category_weights?: Record<string, number> | null;
  default_transport?: Transport | null;
  /** 목 핸들러가 주는 화면 모양 */
  transport?: Transport | null;
}

/** GET /auth/providers 항목: enabled = 서버에 client id 와 secret 이 모두 설정됨 */
export interface AuthProviderStatus {
  provider: OAuthProvider;
  enabled: boolean;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
}

// ── 챗봇 ────────────────────────────────────────────────────
export interface ChatSession {
  id: string;
  created_at: string;
}

// ── 관리자 ──────────────────────────────────────────────────
// 여기 타입은 "화면이 쓰는 모양"이다. 실제 API(apps/api/app/schemas/admin.py)의 필드명·모양은 다르고,
// `lib/api/admin.ts` 의 어댑터가 읽을 때(wire → 화면)·쓸 때(화면 → API 본문) 양쪽을 맞춘다.
// API 가 주지 않는 값은 null/undefined 로 두고 화면이 "-" 나 "준비 중" 으로 보여준다 (지어내지 않는다).
export type PlaceStatus = "pending" | "approved" | "rejected" | "hidden" | "closed";

export interface AdminPlace {
  id: string;
  name: string;
  status: PlaceStatus;
  category: string;
  category_name: string;
  course_role: CourseRole | null;
  region: { slug: string; name: string } | null;
  /** API 는 null 을 줄 수 있다 → 어댑터가 "" 로 바꾼다 */
  address: string;
  lat: number;
  lng: number;
  price_per_person: number | null;
  is_free: boolean;
  rating: number | null;
  review_count: number;
  /** 태그 이름. API 는 {이름: 가중치} 로 주고받는다 → 가중치는 `tag_weights` 에 두고 저장할 때 되돌려 쓴다 */
  tags: string[];
  tag_weights?: Record<string, number>;
  /** 수집 출처를 ", " 로 이은 표시용 문자열 (API `sources[]`) */
  source: string;
  /** 0~1. 실제 API 만 준다 */
  data_quality?: number;
  created_at: string;
  updated_at: string;
  /** 수집 원본과 정규화 결과 — 승인 화면에서 나란히 비교한다 (실제 API 는 아직 주지 않는다) */
  source_raw?: Record<string, unknown>;
  normalized?: Record<string, unknown>;
  duplicate_of?: { id: string; name: string } | null;
}

export type AdminPlaceInput = Partial<
  Pick<
    AdminPlace,
    "name" | "category" | "address" | "lat" | "lng" | "price_per_person" | "is_free" | "tags" | "status"
  >
> & {
  region?: string;
  description?: string;
  /** API 에 받는 필드가 없다 → 어댑터가 보내지 않는다 (목 전용) */
  opening_hours?: string;
  /** 기존 태그의 가중치. 같은 이름의 태그는 이 값을 그대로 돌려보낸다 (새 태그는 1) */
  tag_weights?: Record<string, number>;
};

export interface PlaceRevision {
  id: string;
  actor: string;
  created_at: string;
  changes: Record<string, { from: unknown; to: unknown }>;
  /** create | approve | reject | edit | merge … (API `action`) */
  action?: string;
  note?: string | null;
}

export interface AdminEvent {
  id: string;
  title: string;
  /** 카테고리 코드 (API `category`, 예: culture.festival) */
  type: string;
  region: string | null;
  region_name?: string | null;
  /** API `address` */
  venue: string;
  lat?: number;
  lng?: number;
  starts_on: string;
  ends_on: string;
  is_free: boolean;
  price: number | null;
  /** API `booking_url` */
  link_url: string | null;
  /** API 는 pending | approved | ended → 어댑터가 draft | published | ended 로 옮긴다 */
  status: "draft" | "published" | "ended";
  /** 수집 출처 (admin = 직접 등록) */
  provider?: string;
  /** docs/34: 대학 축제면 그 캠퍼스 id (등록할 때만). 위치를 비우면 캠퍼스에 선다 */
  university?: string | null;
  university_name?: string | null;
  /** "HH:MM" — 있으면 코스가 이 시간 안에서만 행사를 넣는다 */
  start_time?: string | null;
  end_time?: string | null;
  /** 같은 날 한 학교에 행사가 여럿이면 높은 것이 하루의 중심 */
  priority?: number;
}
export type AdminEventInput = Omit<AdminEvent, "id" | "status" | "region_name" | "provider"> & {
  status?: AdminEvent["status"];
};

export interface AdminBanner {
  id: string;
  title: string;
  /** API 에 없는 필드 — 실제 API 에서는 항상 null */
  subtitle: string | null;
  image_url: string | null;
  link_url: string;
  placement: string;
  region: string | null;
  /** null = 기한 없음 */
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
  /** API 가 아직 집계하지 않으면 null */
  impressions: number | null;
  clicks: number | null;
  priority?: number;
}
export type AdminBannerInput = Omit<AdminBanner, "id" | "impressions" | "clicks">;

/** API: draft | collecting | active | paused. ready · failed 는 목에만 있다 */
export type RegionStatus = "draft" | "collecting" | "ready" | "active" | "paused" | "failed";

export interface AdminRegion {
  slug: string;
  name: string;
  parent: string | null;
  level: number;
  center: LatLng;
  radius_m: number;
  keywords: string[];
  status: RegionStatus;
  /** 전체 장소 수 (API `place_counts` 의 합) */
  place_count: number;
  pending_count: number;
  /** 승인된 장소 수 — 1곳 이상이어야 활성화할 수 있다. 목은 주지 않는다 */
  approved_count?: number;
  last_collected_at: string | null;
  last_job?: { id: string; status: "queued" | "running" | "succeeded" | "failed"; progress: number } | null;
}

export interface AdminRegionInput {
  slug: string;
  name: string;
  parent?: string | null;
  /** 1 시·도 · 2 시·군·구 · 3 동네. API 필수값 — 없으면 어댑터가 3 으로 보낸다 */
  level?: number;
  center: LatLng;
  radius_m: number;
  keywords: string[];
}

export interface ScoringProfile {
  purpose: string;
  version: number;
  /** 키는 API 가 정한다 (`FEATURE_KEYS`). 화면은 받은 키를 전부 그린다 */
  weights: Record<string, number>;
  params: Record<string, unknown>;
  experiment_key: string | null;
  is_active?: boolean;
  /** API 는 아직 주지 않는다 → 없으면 화면이 그 줄을 숨긴다 */
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface TemplateSlot {
  /** API `course_role` */
  role: CourseRole;
  budget_share: number;
  /** API 에 없는 값 (목 전용) → 없으면 화면이 열을 숨긴다 */
  stay_min?: number;
  is_optional: boolean;
  is_order_flexible: boolean;
  /** 아래 셋은 화면에서 고치지 않지만 저장할 때 그대로 돌려보낸다 (슬롯은 통째로 교체되므로 빼면 사라진다) */
  earliest_start?: string | null;
  latest_start?: string | null;
  min_slot_budget?: number | null;
}

export interface CourseTemplate {
  /** API 는 `code` 로 식별한다 → 어댑터가 id = code 로 채운다 */
  id: string;
  code?: string;
  name: string;
  purpose: string;
  time_band: string;
  min_budget_per_person: number;
  /** API `party_min` / `party_max` */
  party_size_min: number;
  party_size_max: number;
  slots: TemplateSlot[];
  is_active: boolean;
}

export interface IngestionJob {
  id: string;
  region: string;
  provider: string;
  status: "queued" | "running" | "succeeded" | "failed";
  /** 0~1. API 는 진행률을 주지 않는다 → 끝난 잡만 1 */
  progress: number;
  /** API `fetched_count` */
  collected: number;
  created_count?: number;
  updated_count?: number;
  failed_count?: number;
  job_type?: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface UserAnalytics {
  range: { from: string; to: string };
  totals: { users: number; dau: number; wau: number; mau: number; new_users: number; stickiness: number };
  daily: { date: string; dau: number; new_users: number }[];
  acquisition: { channel: string; users: number }[];
  providers: { provider: string; users: number }[];
  /** 주차별 리텐션 코호트: retention[i] = i주차 잔존율(0~1) */
  cohorts: { cohort: string; size: number; retention: number[] }[];
}

/** null = API 가 아직 집계하지 않는 값. 화면은 "-" 또는 "준비 중" 으로 보여준다 (0 으로 채우지 않는다) */
export interface RecommendationAnalytics {
  range: { from: string; to: string };
  totals: {
    generated: number;
    save_rate: number;
    reroll_rate: number;
    swap_rate: number | null;
    avg_budget: number | null;
    avg_budget_per_person?: number | null;
    avg_budget_utilization: number | null;
    slot_empty_rate: number;
    p95_latency_ms: number | null;
    p50_latency_ms?: number | null;
  };
  daily: { date: string; generated: number; saved: number; rerolled: number }[] | null;
  by_purpose: { purpose: string; purpose_name: string; generated: number; save_rate: number | null }[];
  budget_histogram: { bucket: string; count: number }[] | null;
  heatmap: { region: string; region_name: string; purpose: string; purpose_name: string; count: number }[];
  latency: { date: string; p50: number; p95: number }[] | null;
}

export interface TopPlace {
  id: string;
  name: string;
  region_name: string;
  category_name: string;
  /** API `recommend_count` */
  impressions: number;
  /** API `save_count` */
  saves: number;
  /** API 가 아직 집계하지 않으면 null */
  swap_outs: number | null;
}

export interface SystemHealth {
  status: "ok" | "degraded" | "down";
  services: {
    name: string;
    /** disabled = 설정하지 않아 꺼 둔 구성 요소 (대체 경로로 동작) */
    status: "ok" | "degraded" | "down" | "disabled";
    latency_ms: number | null;
    /** 실제로 붙어 있는 백엔드 (예: sqlite, memory, sql-fallback) */
    backend?: string | null;
  }[];
  checked_at: string;
}

// ── Route Intelligence (docs/27): GET /courses/{id}/route ────────────────────────
/** naver = 네이버 Directions(자동차) · osrm = 실제 보행 경로 · estimate = 엔진 추정(직선 × 우회) · unavailable = 계산 못 함 */
export type RouteLegSource = "naver" | "osrm" | "estimate" | "unavailable";

export interface RouteStop {
  sequence: number;
  place_id: string;
  name: string;
  address: string | null;
  lat: number | null;
  lng: number | null;
  arrive_at: string;
  leave_at: string;
  stay_min: number;
  price: number;
}

/** to_seq 번째 장소로 들어오는 구간 */
export interface RouteLeg {
  from_seq: number;
  to_seq: number;
  origin: string;
  destination: string;
  mode: Transport;
  distance_m: number | null;
  duration_min: number | null;
  /** [lat, lng] */
  path: [number, number][];
  source: RouteLegSource;
  geometry: "road" | "straight" | "none";
  hop_to: string | null;
}

export interface RouteIssue {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  stop: number | null;
  leg: number | null;
}

export interface CourseRoute {
  course_id: string;
  transport: Transport;
  stops: RouteStop[];
  legs: RouteLeg[];
  totals: { travel_min: number; distance_m: number; measured: boolean };
  issues: RouteIssue[];
  feasible: boolean;
  providers: { walk: "osrm" | "estimate"; car: "naver" | "estimate"; transit: "estimate" };
  computed_at: string;
}
