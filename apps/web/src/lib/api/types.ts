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

/** GET /meta/features — 이 환경에서 실제로 되는 기능. 안 되는 기능의 입구는 미리 접는다. */
export interface Features {
  /** LLM 제공자가 설정돼 있을 때만 true */
  chat: boolean;
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

export interface GenerateCourseRequest {
  region?: string;
  origin?: LatLng;
  /** origin 의 표시 이름(역·장소). 결과 화면 머리말과 "다시 짜기"에 그대로 돌아온다 */
  origin_label?: string;
  purpose: string;
  party_size: number;
  budget_total: number;
  start_at?: string;
  duration_min?: number;
  /** efficient = 가깝고 알뜰하게(기본) · fun = 붐비는 거리·놀거리 위주 */
  style?: CourseStyle;
  transport?: Transport;
  include_roles?: CourseRole[];
  preferences?: {
    liked_tags?: string[];
    disliked_tags?: string[];
    exclude_place_ids?: string[];
  };
  alternatives?: number;
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
}

export interface TravelLeg {
  travel_min: number;
  distance_m: number;
  mode: Transport;
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
  congestion: Congestion | null;
}

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
    preferences?: { liked_tags: string[]; disliked_tags: string[] };
    purpose: { code: string; name: string };
    party_size: number;
    budget_total: number;
    transport: Transport;
    start_at: string;
    /** 사용자가 정한 만남 시간(분). 맡겼으면 null */
    duration_min?: number | null;
    style?: CourseStyle;
  };
  /** 같은 요청에서 나온 대안 코스들(자기 자신 포함, 탭 순서) */
  siblings: { id: string; label: string }[];
  nearby_events: NearbyEvent[];
  meta?: GenerateMeta;
  og: { title: string; description: string; image_url: string | null };
  is_saved?: boolean;
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

export type ChatStreamEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; arguments?: Record<string, unknown> } }
  | { event: "course"; data: Course }
  | { event: "done"; data: { message_id?: string } }
  | { event: "error"; data: ProblemDetails };

// ── 관리자 ──────────────────────────────────────────────────
export type PlaceStatus = "pending" | "approved" | "rejected" | "hidden";

export interface AdminPlace {
  id: string;
  name: string;
  status: PlaceStatus;
  category: string;
  category_name: string;
  course_role: CourseRole | null;
  region: { slug: string; name: string } | null;
  address: string;
  lat: number;
  lng: number;
  price_per_person: number | null;
  is_free: boolean;
  rating: number | null;
  review_count: number;
  tags: string[];
  source: string;
  created_at: string;
  updated_at: string;
  /** 수집 원본과 정규화 결과 — 승인 화면에서 나란히 비교한다 */
  source_raw?: Record<string, unknown>;
  normalized?: Record<string, unknown>;
  duplicate_of?: { id: string; name: string } | null;
}

export type AdminPlaceInput = Partial<
  Pick<
    AdminPlace,
    "name" | "category" | "address" | "lat" | "lng" | "price_per_person" | "is_free" | "tags" | "status"
  >
> & { region?: string; description?: string; opening_hours?: string };

export interface PlaceRevision {
  id: string;
  actor: string;
  created_at: string;
  changes: Record<string, { from: unknown; to: unknown }>;
}

export interface AdminEvent {
  id: string;
  title: string;
  type: string;
  region: string | null;
  region_name?: string | null;
  venue: string;
  starts_on: string;
  ends_on: string;
  is_free: boolean;
  price: number | null;
  link_url: string | null;
  status: "draft" | "published" | "ended";
}
export type AdminEventInput = Omit<AdminEvent, "id" | "status" | "region_name"> & {
  status?: AdminEvent["status"];
};

export interface AdminBanner {
  id: string;
  title: string;
  subtitle: string | null;
  image_url: string | null;
  link_url: string;
  placement: string;
  region: string | null;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
  impressions: number;
  clicks: number;
}
export type AdminBannerInput = Omit<AdminBanner, "id" | "impressions" | "clicks">;

export type RegionStatus = "draft" | "collecting" | "ready" | "active" | "failed";

export interface AdminRegion {
  slug: string;
  name: string;
  parent: string | null;
  level: number;
  center: LatLng;
  radius_m: number;
  keywords: string[];
  status: RegionStatus;
  place_count: number;
  pending_count: number;
  last_collected_at: string | null;
  last_job?: { id: string; status: "queued" | "running" | "succeeded" | "failed"; progress: number } | null;
}

export interface AdminRegionInput {
  slug: string;
  name: string;
  parent?: string | null;
  center: LatLng;
  radius_m: number;
  keywords: string[];
}

export interface ScoringProfile {
  purpose: string;
  version: number;
  weights: ScoreBreakdown;
  params: Record<string, unknown>;
  experiment_key: string | null;
  updated_at: string;
  updated_by: string | null;
}

export interface TemplateSlot {
  role: CourseRole;
  budget_share: number;
  stay_min: number;
  is_optional: boolean;
  is_order_flexible: boolean;
}

export interface CourseTemplate {
  id: string;
  name: string;
  purpose: string;
  time_band: string;
  min_budget_per_person: number;
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
  progress: number;
  collected: number;
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

export interface RecommendationAnalytics {
  range: { from: string; to: string };
  totals: {
    generated: number;
    save_rate: number;
    reroll_rate: number;
    swap_rate: number;
    avg_budget: number;
    avg_budget_utilization: number;
    slot_empty_rate: number;
    p95_latency_ms: number;
  };
  daily: { date: string; generated: number; saved: number; rerolled: number }[];
  by_purpose: { purpose: string; purpose_name: string; generated: number; save_rate: number }[];
  budget_histogram: { bucket: string; count: number }[];
  heatmap: { region: string; region_name: string; purpose: string; purpose_name: string; count: number }[];
  latency: { date: string; p50: number; p95: number }[];
}

export interface TopPlace {
  id: string;
  name: string;
  region_name: string;
  category_name: string;
  impressions: number;
  saves: number;
  swap_outs: number;
}

export interface SystemHealth {
  status: "ok" | "degraded" | "down";
  services: { name: string; status: "ok" | "degraded" | "down"; latency_ms: number | null }[];
  checked_at: string;
}
