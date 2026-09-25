"use client";

/**
 * 관리자 API 훅 — docs/03-api-spec.md §7.
 * 전부 `/admin/*` 이고 서버에서 role ∈ {admin, operator} 를 검증한다. 화면은 403 을 짠이 에러 상태로 보여준다.
 *
 * ── 어댑터 ──
 * 계약은 실제 API 다 (`apps/api/app/schemas/admin.py`, 요청 모델은 전부 extra="forbid").
 * 화면 타입(`types.ts` 관리자 절)은 목 픽스처와 같은 모양이라, 이 파일이 양쪽을 맞춘다.
 *   읽기: `to*` 함수가 wire → 화면 타입. 목이 주는 화면 모양이 와도 그대로 통과시킨다.
 *   쓰기: `*Body` 함수가 화면 입력 → API 본문. 목 모드(`IS_MOCKING`)에서는 목 핸들러가 기대하는 화면 모양을 그대로 보낸다.
 * API 가 주지 않는 값은 null 로 둔다 — 0 이나 가짜 값으로 채우지 않는다.
 */
import { useCallback, useMemo } from "react";
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ApiError, IS_MOCKING, api, newIdempotencyKey } from "./client";
import { useCategories, usePurposes } from "./hooks";
import {
  SCORE_FEATURES,
  type AdminBanner,
  type AdminBannerInput,
  type AdminEvent,
  type AdminEventInput,
  type AdminPlace,
  type AdminPlaceInput,
  type AdminRegion,
  type AdminRegionInput,
  type Category,
  type CourseRole,
  type CourseTemplate,
  type IngestionJob,
  type ItemList,
  type Page,
  type PlaceRevision,
  type PlaceStatus,
  type RecommendationAnalytics,
  type ScoringProfile,
  type SystemHealth,
  type TemplateSlot,
  type TopPlace,
  type UserAnalytics,
} from "./types";

// ── types.ts 에 없는 것만 여기서 정의한다 ─────────────────────
/** 목록 응답에 서버가 전체 개수를 같이 주면(선택) 대시보드 배지에 쓴다 */
export type AdminPlacePage = Page<AdminPlace> & { total?: number };

export interface AdminPlaceListParams {
  status?: PlaceStatus;
  q?: string;
  region?: string;
  limit?: number;
  cursor?: string;
}

export interface BulkApproveResult {
  approved: number;
  failed: string[];
}

/** 파일 업로드는 API 에서 바로 실행돼 끝난 잡으로 돌아온다 */
export interface ImportResult {
  job_id: string;
  /** 파일에서 읽은 건수 (API `fetched_count`) */
  accepted: number;
  created?: number;
  updated?: number;
  failed?: number;
  status?: IngestionJob["status"];
}

export interface PresignResult {
  upload_url: string;
  public_url: string;
  fields?: Record<string, string>;
}

export interface TagAffinity {
  tag: string;
  /** -1(어울리지 않음) ~ 1(잘 어울림) */
  affinity: number;
}

export type AdminRegionPatch = Partial<Omit<AdminRegionInput, "slug">>;
export type CourseTemplateInput = Omit<CourseTemplate, "id">;

export interface DateRange {
  from?: string;
  to?: string;
}

/**
 * 지역 수집에 쓸 수 있는 공식 API 출처 (API `API_PROVIDERS`). `POST /admin/regions/{slug}/collect` 는
 * providers 를 1개 이상 요구한다. 파일 업로드는 "관광지 추가" 화면의 가져오기가 따로 맡는다.
 */
export const COLLECT_PROVIDERS = [
  { value: "kakao_local", label: "카카오 로컬" },
  { value: "tourapi", label: "한국관광공사 TourAPI" },
  { value: "naver_search", label: "네이버 검색" },
  { value: "google_places", label: "Google Places" },
  { value: "data_go_kr", label: "공공데이터포털" },
] as const;
export const DEFAULT_COLLECT_PROVIDERS: string[] = ["kakao_local", "tourapi"];

const PROVIDER_LABEL: Record<string, string> = {
  ...Object.fromEntries(COLLECT_PROVIDERS.map((p) => [p.value, p.label])),
  file: "파일 업로드",
  admin: "직접 등록",
  user: "사용자 제보",
  seed: "기본 데이터",
};
/** 수집 출처 코드 → 운영자에게 보여 줄 이름. 모르는 값은 그대로. */
export const providerLabel = (code: string) => PROVIDER_LABEL[code] ?? code;

export const adminKeys = {
  all: ["admin"] as const,
  places: (params: AdminPlaceListParams) => ["admin", "places", params] as const,
  placesRoot: ["admin", "places"] as const,
  revisions: (id: string) => ["admin", "places", id, "revisions"] as const,
  events: ["admin", "events"] as const,
  banners: ["admin", "banners"] as const,
  regions: ["admin", "regions"] as const,
  scoring: (purpose: string) => ["admin", "scoring", purpose] as const,
  templates: (purpose?: string) => ["admin", "templates", purpose ?? "all"] as const,
  templatesRoot: ["admin", "templates"] as const,
  affinities: (purpose: string) => ["admin", "affinities", purpose] as const,
  jobs: ["admin", "ingestion", "jobs"] as const,
  userAnalytics: (range: DateRange) => ["admin", "analytics", "users", range] as const,
  recAnalytics: (range: DateRange) => ["admin", "analytics", "recommendations", range] as const,
  topPlaces: ["admin", "analytics", "places", "top"] as const,
  health: ["admin", "system", "health"] as const,
};

const enc = encodeURIComponent;

// ── 공통 어댑터 도구 ─────────────────────────────────────────
type Raw = Record<string, unknown>;
const str = (v: unknown, fallback = ""): string => (typeof v === "string" ? v : fallback);
const strOrNull = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const numOr = (v: unknown, fallback: number): number => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
const numOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const isRecord = (v: unknown): v is Raw => typeof v === "object" && v !== null && !Array.isArray(v);
const list = (v: unknown): Raw[] => (isRecord(v) && Array.isArray(v.items) ? (v.items as Raw[]) : []);
/** undefined 인 키는 본문에서 뺀다 (PATCH 는 "보낸 것만 바꾼다") */
const compact = <T extends Raw>(body: T): T => Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined)) as T;
/** 목 핸들러는 화면 모양의 본문을 기대한다 */
const body = (ui: unknown, wire: unknown): unknown => (IS_MOCKING ? ui : wire);

/** ISO 시각 → KST 기준 YYYY-MM-DD (date input 용). UTC 로 자르면 자정 근처에서 하루가 밀린다 */
export function kstDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : new Date(d.getTime() + 9 * 3_600_000).toISOString().slice(0, 10);
}
/** date input 값(YYYY-MM-DD) → KST 하루의 시작/끝. 이미 시각이 붙어 있으면 그대로 */
const kstBoundary = (value: string | null | undefined, end: boolean): string | null | undefined =>
  !value ? (value === undefined ? undefined : null) : value.length === 10 ? `${value}T${end ? "23:59:59" : "00:00:00"}+09:00` : value;

// ── 코드 → 이름 (지역·분류·목적) ─────────────────────────────
// API 는 slug·code 만 준다. 운영자에게는 한글 이름을 보여야 하므로, 이미 있는 목록 API 로 이름을 찾는다.
export interface AdminLabels {
  region: (slug: string) => string;
  category: (code: string) => string;
  categoryRole: (code: string) => CourseRole | null;
  purpose: (code: string) => string;
}

const regionsQuery = {
  queryKey: adminKeys.regions,
  queryFn: async ({ signal }: { signal: AbortSignal }): Promise<ItemList<AdminRegion>> => ({
    items: list(await api.get("/admin/regions", { signal })).map(toAdminRegion),
  }),
};

function flattenTree(items: Category[]): Category[] {
  return items.flatMap((c) => [c, ...flattenTree(c.children ?? [])]);
}

export function useAdminLabels(): AdminLabels {
  const regions = useQuery<ItemList<AdminRegion>, ApiError>({ ...regionsQuery, staleTime: 60_000 });
  const categories = useCategories();
  const purposes = usePurposes();
  return useMemo(() => {
    const regionNames = new Map((regions.data?.items ?? []).map((r) => [r.slug, r.name]));
    const cats = new Map(flattenTree(categories.data?.items ?? []).map((c) => [c.code, c]));
    const purposeNames = new Map((purposes.data?.items ?? []).map((p) => [p.code, p.name]));
    return {
      region: (slug) => regionNames.get(slug) ?? slug,
      category: (code) => cats.get(code)?.name ?? code,
      categoryRole: (code) => cats.get(code)?.course_role ?? null,
      purpose: (code) => purposeNames.get(code) ?? code,
    };
  }, [regions.data, categories.data, purposes.data]);
}

const NO_LABELS: AdminLabels = { region: (s) => s, category: (c) => c, categoryRole: () => null, purpose: (c) => c };

// ── 장소 승인 · 수정 ────────────────────────────────────────
function toAdminPlace(raw: Raw, labels: AdminLabels): AdminPlace {
  const category = str(raw.category);
  const region = typeof raw.region === "string" ? { slug: raw.region, name: labels.region(raw.region) } : isRecord(raw.region) ? { slug: str(raw.region.slug), name: str(raw.region.name) } : null;
  // API: tags = {이름: 가중치}. 목: string[]
  const tagWeights = isRecord(raw.tags) ? (Object.fromEntries(Object.entries(raw.tags).filter(([, w]) => typeof w === "number")) as Record<string, number>) : undefined;
  const tags = Array.isArray(raw.tags) ? raw.tags.filter((t): t is string => typeof t === "string") : Object.keys(tagWeights ?? {});
  const sources = Array.isArray(raw.sources) ? raw.sources.filter((s): s is string => typeof s === "string") : [];
  const createdAt = str(raw.created_at);
  return {
    id: str(raw.id),
    name: str(raw.name),
    status: str(raw.status, "pending") as PlaceStatus,
    category,
    category_name: strOrNull(raw.category_name) ?? labels.category(category),
    course_role: strOrNull(raw.course_role) ?? labels.categoryRole(category),
    region,
    address: str(raw.address),
    lat: numOr(raw.lat, 0),
    lng: numOr(raw.lng, 0),
    price_per_person: numOrNull(raw.price_per_person),
    is_free: raw.is_free === true,
    rating: numOrNull(raw.rating),
    review_count: numOr(raw.review_count, 0),
    tags,
    tag_weights: tagWeights,
    source: strOrNull(raw.source) ?? (sources.map(providerLabel).join(", ") || "-"),
    data_quality: numOrNull(raw.data_quality) ?? undefined,
    created_at: createdAt,
    updated_at: str(raw.updated_at, createdAt),
    source_raw: isRecord(raw.source_raw) ? raw.source_raw : undefined,
    normalized: isRecord(raw.normalized) ? raw.normalized : undefined,
    duplicate_of: isRecord(raw.duplicate_of) ? { id: str(raw.duplicate_of.id), name: str(raw.duplicate_of.name) } : null,
  };
}

/** API `tags: dict[str, float]`. 기존 태그는 가중치를 지키고 새로 적은 태그는 1 */
const tagsBody = (input: AdminPlaceInput): Record<string, number> | undefined =>
  input.tags === undefined ? undefined : Object.fromEntries(input.tags.map((name) => [name, input.tag_weights?.[name] ?? 1]));

/** `AdminPlacePatch` — 지역·운영 시간은 받지 않는다 */
const placePatchBody = (input: AdminPlaceInput) =>
  compact({
    name: input.name,
    category: input.category,
    lat: input.lat,
    lng: input.lng,
    address: input.address === undefined ? undefined : input.address || null,
    description: input.description,
    price_per_person: input.is_free ? undefined : input.price_per_person,
    is_free: input.is_free,
    status: input.status,
    tags: tagsBody(input),
  });

/** `AdminPlaceCreate` — status 는 받지 않는다 (직접 등록은 서버가 바로 승인 상태로 만든다) */
const placeCreateBody = (input: AdminPlaceInput) =>
  compact({
    region: input.region,
    category: input.category,
    name: input.name,
    lat: input.lat,
    lng: input.lng,
    address: input.address || undefined,
    description: input.description || undefined,
    price_per_person: input.is_free ? undefined : (input.price_per_person ?? undefined),
    is_free: input.is_free ?? false,
    tags: tagsBody(input) ?? {},
  });

export function useAdminPlaces(params: AdminPlaceListParams) {
  const labels = useAdminLabels();
  return useQuery<Raw, ApiError, AdminPlacePage>({
    queryKey: adminKeys.places(params),
    queryFn: ({ signal }) => api.get("/admin/places", { query: { ...params }, signal }),
    // 이름 목록이 나중에 도착해도 다시 그리도록 캐시에는 wire 를 두고 select 에서 옮긴다
    select: useCallback(
      (raw: Raw): AdminPlacePage => ({
        items: list(raw).map((p) => toAdminPlace(p, labels)),
        next_cursor: strOrNull(raw.next_cursor),
        total: numOrNull(raw.total) ?? undefined,
      }),
      [labels],
    ),
    placeholderData: keepPreviousData,
  });
}

function toRevision(raw: Raw): PlaceRevision {
  if (isRecord(raw.changes)) return raw as unknown as PlaceRevision; // 목
  const before = isRecord(raw.before) ? raw.before : {};
  const after = isRecord(raw.after) ? raw.after : {};
  const changes: PlaceRevision["changes"] = {};
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) changes[key] = { from: before[key], to: after[key] };
  }
  return {
    id: String(raw.id),
    actor: typeof raw.admin_id === "number" ? `운영자 #${raw.admin_id}` : "시스템",
    created_at: str(raw.created_at),
    changes,
    action: strOrNull(raw.action) ?? undefined,
    note: strOrNull(raw.note),
  };
}

export function usePlaceRevisions(id: string | undefined) {
  return useQuery<ItemList<PlaceRevision>, ApiError>({
    queryKey: adminKeys.revisions(id ?? ""),
    queryFn: async ({ signal }) => ({ items: list(await api.get(`/admin/places/${enc(id ?? "")}/revisions`, { signal })).map(toRevision) }),
    enabled: Boolean(id),
  });
}

function useInvalidatePlaces() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminKeys.placesRoot });
    void client.invalidateQueries({ queryKey: adminKeys.regions }); // 지역별 장소 수·승인 대기 수가 바뀐다
  };
}

export function useApprovePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, string>({
    mutationFn: async (id) => toAdminPlace(await api.post<Raw>(`/admin/places/${enc(id)}/approve`), NO_LABELS),
    onSuccess: invalidate,
  });
}

export function useRejectPlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, { id: string; reason?: string }>({
    mutationFn: async ({ id, reason }) => toAdminPlace(await api.post<Raw>(`/admin/places/${enc(id)}/reject`, body({ reason }, compact({ note: reason }))), NO_LABELS),
    onSuccess: invalidate,
  });
}

export function useBulkApprovePlaces() {
  const invalidate = useInvalidatePlaces();
  return useMutation<BulkApproveResult, ApiError, string[]>({
    mutationFn: async (ids) => {
      const raw = await api.post<Raw>("/admin/places/bulk-approve", { ids });
      // API: {updated, not_found}
      return {
        approved: numOr(raw.approved, numOr(raw.updated, 0)),
        failed: (Array.isArray(raw.failed) ? raw.failed : Array.isArray(raw.not_found) ? raw.not_found : []).map(String),
      };
    },
    onSuccess: invalidate,
  });
}

export function useUpdatePlace() {
  const client = useQueryClient();
  return useMutation<AdminPlace, ApiError, { id: string; input: AdminPlaceInput }>({
    mutationFn: async ({ id, input }) => toAdminPlace(await api.patch<Raw>(`/admin/places/${enc(id)}`, body(input, placePatchBody(input))), NO_LABELS),
    onSuccess: (_place, { id }) => {
      void client.invalidateQueries({ queryKey: adminKeys.placesRoot });
      void client.invalidateQueries({ queryKey: adminKeys.revisions(id) });
    },
  });
}

/** 그 장소의 실제 사진 올리기 (JPEG · PNG · WebP, 6MB 이하). 공공데이터에 사진이 없는 97% 를 메우는 유일한 길이다 */
export const MAX_PHOTO_BYTES = 6 * 1024 * 1024;
export function useUploadPlacePhoto() {
  const client = useQueryClient();
  return useMutation<AdminPlace, ApiError, { id: string; file: File; makeCover: boolean }>({
    mutationFn: async ({ id, file, makeCover }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("make_cover", makeCover ? "true" : "false");
      return toAdminPlace(await api.post<Raw>(`/admin/places/${enc(id)}/photos`, form, { timeoutMs: 60_000 }), NO_LABELS);
    },
    onSuccess: (_place, { id }) => {
      void client.invalidateQueries({ queryKey: ["place", id] });
      void client.invalidateQueries({ queryKey: adminKeys.revisions(id) });
    },
  });
}

/** `id` 를 `into` 로 합친다. API 는 남는 쪽이 경로, 흡수되는 쪽이 본문이다: POST /places/{into}/merge {duplicate_id: id} */
export function useMergePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, { id: string; into: string }>({
    mutationFn: async ({ id, into }) =>
      toAdminPlace(IS_MOCKING ? await api.post<Raw>(`/admin/places/${enc(id)}/merge`, { into }) : await api.post<Raw>(`/admin/places/${enc(into)}/merge`, { duplicate_id: id }), NO_LABELS),
    onSuccess: invalidate,
  });
}

/** 관광지·문화공간 직접 추가 (category 의 course_role = ATTRACTION / CULTURE) */
export function useCreatePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, AdminPlaceInput>({
    mutationFn: async (input) => toAdminPlace(await api.post<Raw>("/admin/places", body(input, placeCreateBody(input)), { idempotencyKey: newIdempotencyKey() }), NO_LABELS),
    onSuccess: invalidate,
  });
}

/** CSV/JSON 업로드 → `file` provider 수집 잡. API 는 `region` 폼 필드가 필수다 */
export function useImportPlaces() {
  const client = useQueryClient();
  return useMutation<ImportResult, ApiError, { file: File; region: string }>({
    mutationFn: async ({ file, region }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("region", region);
      const raw = await api.post<Raw>("/admin/places/import", form, { timeoutMs: 60_000 });
      if (typeof raw.job_id === "string") return raw as unknown as ImportResult; // 목
      const job = toJob(raw);
      return { job_id: job.id, accepted: job.collected, created: job.created_count, updated: job.updated_count, failed: job.failed_count, status: job.status };
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.jobs });
      void client.invalidateQueries({ queryKey: adminKeys.placesRoot });
      void client.invalidateQueries({ queryKey: adminKeys.regions });
    },
  });
}

// ── 이벤트 ──────────────────────────────────────────────────
// 화면 상태 ↔ API 상태: 초안 = pending(검수 전), 게시 중 = approved
const EVENT_STATUS_IN: Record<string, AdminEvent["status"]> = { pending: "draft", approved: "published", ended: "ended" };
const EVENT_STATUS_OUT: Record<AdminEvent["status"], string> = { draft: "pending", published: "approved", ended: "ended" };

function toAdminEvent(raw: Raw, labels: AdminLabels): AdminEvent {
  const status = str(raw.status);
  const region = strOrNull(raw.region);
  return {
    id: str(raw.id),
    title: str(raw.title),
    type: str(raw.type, str(raw.category)),
    region,
    region_name: strOrNull(raw.region_name) ?? (region ? labels.region(region) : null),
    venue: str(raw.venue, str(raw.address)),
    lat: numOrNull(raw.lat) ?? undefined,
    lng: numOrNull(raw.lng) ?? undefined,
    starts_on: str(raw.starts_on),
    ends_on: str(raw.ends_on),
    is_free: raw.is_free === true,
    price: numOrNull(raw.price),
    link_url: strOrNull(raw.link_url) ?? strOrNull(raw.booking_url),
    status: EVENT_STATUS_IN[status] ?? (status as AdminEvent["status"]),
    provider: strOrNull(raw.provider) ?? undefined,
    university: strOrNull(raw.university),
    university_name: strOrNull(raw.university_name),
    start_time: strOrNull(raw.start_time),
    end_time: strOrNull(raw.end_time),
    priority: numOrNull(raw.priority) ?? 0,
  };
}

/** `EventPatch` 가 받는 것만. 지역·유형·좌표는 등록 뒤에 바꿀 수 없다 */
const eventPatchBody = (input: AdminEventInput) =>
  compact({
    title: input.title,
    address: input.venue || null,
    starts_on: input.starts_on,
    ends_on: input.ends_on,
    price: input.is_free ? null : input.price,
    is_free: input.is_free,
    booking_url: input.link_url || null,
    status: input.status ? EVENT_STATUS_OUT[input.status] : undefined,
    start_time: input.start_time || null,
    end_time: input.end_time || null,
    priority: input.priority ?? undefined,
  });

/** `EventIn` — region · lat · lng 필수 */
const eventCreateBody = (input: AdminEventInput) =>
  compact({ ...eventPatchBody(input), region: input.region ?? undefined, category: input.type || null, lat: input.lat, lng: input.lng, university: input.university || undefined });

export function useAdminEvents() {
  const labels = useAdminLabels();
  return useQuery<Raw, ApiError, Page<AdminEvent>>({
    queryKey: adminKeys.events,
    queryFn: ({ signal }) => api.get("/admin/events", { query: { limit: 100 }, signal }),
    select: useCallback((raw: Raw): Page<AdminEvent> => ({ items: list(raw).map((e) => toAdminEvent(e, labels)), next_cursor: strOrNull(raw.next_cursor) }), [labels]),
  });
}

export function useSaveEvent() {
  const client = useQueryClient();
  return useMutation<AdminEvent, ApiError, { id?: string; input: AdminEventInput }>({
    mutationFn: async ({ id, input }) =>
      toAdminEvent(id ? await api.patch<Raw>(`/admin/events/${enc(id)}`, body(input, eventPatchBody(input))) : await api.post<Raw>("/admin/events", body(input, eventCreateBody(input))), NO_LABELS),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.events }),
  });
}

export function useDeleteEvent() {
  const client = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/admin/events/${enc(id)}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.events }),
  });
}

// ── 배너 ────────────────────────────────────────────────────
function toAdminBanner(raw: Raw): AdminBanner {
  return {
    id: String(raw.id), // API 는 정수 id
    title: str(raw.title),
    subtitle: strOrNull(raw.subtitle),
    image_url: strOrNull(raw.image_url),
    link_url: str(raw.link_url),
    placement: str(raw.placement, "home"),
    region: strOrNull(raw.region),
    starts_at: strOrNull(raw.starts_at),
    ends_at: strOrNull(raw.ends_at),
    is_active: raw.is_active === true,
    impressions: numOrNull(raw.impressions),
    clicks: numOrNull(raw.clicks),
    priority: numOrNull(raw.priority) ?? undefined,
  };
}

/** `BannerIn` / `BannerPatch` — subtitle 은 없는 필드, region 은 만들 때만 받는다 */
const bannerBody = (input: Partial<AdminBannerInput>, creating: boolean) =>
  compact({
    title: input.title,
    image_url: input.image_url ?? undefined,
    link_url: input.link_url === undefined ? undefined : input.link_url || null,
    placement: input.placement,
    region: creating ? (input.region ?? undefined) : undefined,
    starts_at: kstBoundary(input.starts_at, false),
    ends_at: kstBoundary(input.ends_at, true),
    priority: input.priority,
    is_active: input.is_active,
  });

export function useAdminBanners() {
  return useQuery<Page<AdminBanner>, ApiError>({
    queryKey: adminKeys.banners,
    queryFn: async ({ signal }) => {
      const raw = await api.get<Raw>("/admin/banners", { query: { limit: 100 }, signal });
      return { items: list(raw).map(toAdminBanner), next_cursor: strOrNull(raw.next_cursor) };
    },
  });
}

export function useSaveBanner() {
  const client = useQueryClient();
  return useMutation<AdminBanner, ApiError, { id?: string; input: Partial<AdminBannerInput> }>({
    mutationFn: async ({ id, input }) =>
      toAdminBanner(id ? await api.patch<Raw>(`/admin/banners/${enc(id)}`, body(input, bannerBody(input, false))) : await api.post<Raw>("/admin/banners", body(input, bannerBody(input, true)))),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.banners }),
  });
}

export function useDeleteBanner() {
  const client = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/admin/banners/${enc(id)}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.banners }),
  });
}

/**
 * ⚠️ 실제 API 는 아직 501 (NOT_IMPLEMENTED) 을 준다 — 업로드 저장소(S3)가 연결되지 않았다.
 * 그때까지 화면은 업로드 버튼을 두지 않고 이미지 주소(https)를 직접 받는다.
 */
export function usePresignUpload() {
  return useMutation<PresignResult, ApiError, { filename: string; content_type: string }>({
    mutationFn: (input) => api.post("/admin/uploads/presign", input),
  });
}

// ── 지역 ────────────────────────────────────────────────────
function toAdminRegion(raw: Raw): AdminRegion {
  if (isRecord(raw.center)) return raw as unknown as AdminRegion; // 목
  const counts = isRecord(raw.place_counts) ? raw.place_counts : {};
  const count = (key: string) => numOr(counts[key], 0);
  return {
    slug: str(raw.slug),
    name: str(raw.name),
    parent: strOrNull(raw.parent),
    level: numOr(raw.level, 3),
    center: { lat: numOr(raw.center_lat, 0), lng: numOr(raw.center_lng, 0) },
    radius_m: numOr(raw.radius_m, 0),
    keywords: Array.isArray(raw.search_keywords) ? raw.search_keywords.filter((k): k is string => typeof k === "string") : [],
    status: str(raw.status, "draft") as AdminRegion["status"],
    place_count: Object.keys(counts).reduce((sum, key) => sum + count(key), 0),
    pending_count: count("pending"),
    approved_count: count("approved"),
    last_collected_at: null,
    last_job: null,
  };
}

/** `RegionIn` / `RegionPatch`. 상위 지역·단계는 만들 때만 받는다 */
const regionBody = (input: Partial<AdminRegionInput>, creating: boolean) =>
  compact({
    slug: creating ? input.slug : undefined,
    name: input.name,
    level: creating ? (input.level ?? 3) : undefined,
    parent: creating ? input.parent || null : undefined,
    center_lat: input.center?.lat,
    center_lng: input.center?.lng,
    radius_m: input.radius_m,
    search_keywords: input.keywords,
  });

export function useAdminRegions() {
  return useQuery<ItemList<AdminRegion>, ApiError>({
    ...regionsQuery,
    // 수집 중인 지역이 있으면 3초마다 상태를 다시 읽는다 (목). 실제 API 는 진행률이 없어 30초면 충분하다
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === "collecting") ? (IS_MOCKING ? 3000 : 30_000) : false),
  });
}

function useInvalidateRegions() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminKeys.regions });
    void client.invalidateQueries({ queryKey: adminKeys.jobs });
    void client.invalidateQueries({ queryKey: ["meta", "regions"] });
  };
}

export function useCreateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, AdminRegionInput>({
    mutationFn: async (input) => toAdminRegion(await api.post<Raw>("/admin/regions", body(input, regionBody(input, true)))),
    onSuccess: invalidate,
  });
}

export function useUpdateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, { slug: string; input: AdminRegionPatch }>({
    mutationFn: async ({ slug, input }) => toAdminRegion(await api.patch<Raw>(`/admin/regions/${enc(slug)}`, body(input, regionBody(input, false)))),
    onSuccess: invalidate,
  });
}

/** 출처마다 수집 잡이 1건씩 생긴다 (API 는 목록을 준다). providers 를 비우면 기본 출처로 돌린다 */
export function useCollectRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<IngestionJob[], ApiError, { slug: string; providers?: string[] }>({
    mutationFn: async ({ slug, providers }) => {
      const raw = await api.post<unknown>(`/admin/regions/${enc(slug)}/collect`, IS_MOCKING ? undefined : { providers: providers?.length ? providers : DEFAULT_COLLECT_PROVIDERS });
      return (Array.isArray(raw) ? (raw as Raw[]) : isRecord(raw) ? [raw] : []).map(toJob);
    },
    onSuccess: invalidate,
  });
}

export function useActivateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, string>({
    mutationFn: async (slug) => toAdminRegion(await api.post<Raw>(`/admin/regions/${enc(slug)}/activate`)),
    onSuccess: invalidate,
  });
}

// ── 추천 설정 ───────────────────────────────────────────────
function toScoringProfile(raw: Raw): ScoringProfile {
  const given = isRecord(raw.weights) ? raw.weights : {};
  // 화면이 아는 피처는 0 으로라도 보여 주고(조정할 수 있게), API 가 새로 추가한 키도 버리지 않는다
  const weights: Record<string, number> = Object.fromEntries(SCORE_FEATURES.map((k) => [k, 0]));
  for (const [key, value] of Object.entries(given)) if (typeof value === "number") weights[key] = value;
  return {
    purpose: str(raw.purpose),
    version: numOr(raw.version, 1),
    weights,
    params: isRecord(raw.params) ? raw.params : {},
    experiment_key: strOrNull(raw.experiment_key),
    is_active: typeof raw.is_active === "boolean" ? raw.is_active : undefined,
    updated_at: strOrNull(raw.updated_at),
    updated_by: strOrNull(raw.updated_by),
  };
}

export function useScoringProfile(purpose: string | undefined) {
  return useQuery<ScoringProfile, ApiError>({
    queryKey: adminKeys.scoring(purpose ?? ""),
    queryFn: async ({ signal }) => toScoringProfile(await api.get<Raw>(`/admin/scoring-profiles/${enc(purpose ?? "")}`, { signal })),
    enabled: Boolean(purpose),
  });
}

/** `ScoringProfileBody`. 불러온 프로필의 params · experiment_key · is_active 를 같이 돌려보낸다 (가중치만 바꾼다는 뜻을 분명히) */
export function useUpdateScoringProfile() {
  const client = useQueryClient();
  return useMutation<
    ScoringProfile,
    ApiError,
    { purpose: string; weights: Record<string, number>; params?: Record<string, unknown>; experiment_key?: string | null; is_active?: boolean }
  >({
    mutationFn: async ({ purpose, ...rest }) => toScoringProfile(await api.put<Raw>(`/admin/scoring-profiles/${enc(purpose)}`, compact({ ...rest }))),
    onSuccess: (profile) => client.setQueryData(adminKeys.scoring(profile.purpose), profile),
  });
}

function toSlot(raw: Raw): TemplateSlot {
  return {
    role: str(raw.role, str(raw.course_role)),
    budget_share: numOr(raw.budget_share, 0),
    ...(typeof raw.stay_min === "number" ? { stay_min: raw.stay_min } : {}),
    is_optional: raw.is_optional === true,
    is_order_flexible: raw.is_order_flexible === true,
    ...("course_role" in raw ? { earliest_start: strOrNull(raw.earliest_start), latest_start: strOrNull(raw.latest_start), min_slot_budget: numOrNull(raw.min_slot_budget) } : {}),
  };
}

function toTemplate(raw: Raw): CourseTemplate {
  const code = str(raw.code, str(raw.id));
  return {
    id: str(raw.id, code), // API 는 code 로 식별한다
    code,
    name: str(raw.name),
    purpose: str(raw.purpose),
    time_band: str(raw.time_band),
    min_budget_per_person: numOr(raw.min_budget_per_person, 0),
    party_size_min: numOr(raw.party_size_min, numOr(raw.party_min, 1)),
    party_size_max: numOr(raw.party_size_max, numOr(raw.party_max, 8)),
    slots: Array.isArray(raw.slots) ? (raw.slots as Raw[]).map(toSlot) : [],
    is_active: raw.is_active !== false,
  };
}

/** `SlotBody` — stay_min 은 없는 필드. 시간 제약·최소 예산은 고치지 않아도 되돌려 보내야 지워지지 않는다 */
const slotBody = (slot: TemplateSlot) => ({
  course_role: slot.role,
  budget_share: slot.budget_share,
  is_optional: slot.is_optional,
  is_order_flexible: slot.is_order_flexible,
  earliest_start: slot.earliest_start ?? null,
  latest_start: slot.latest_start ?? null,
  min_slot_budget: slot.min_slot_budget ?? null,
});

const templateBody = (input: Partial<CourseTemplateInput>, creating: boolean) =>
  compact({
    code: creating ? input.code : undefined,
    purpose: creating ? input.purpose : undefined,
    time_band: creating ? input.time_band : undefined,
    name: input.name,
    min_budget_per_person: input.min_budget_per_person,
    party_min: input.party_size_min,
    party_max: input.party_size_max,
    is_active: input.is_active,
    slots: input.slots?.map(slotBody),
  });

export function useTemplates(purpose?: string) {
  return useQuery<ItemList<CourseTemplate>, ApiError>({
    queryKey: adminKeys.templates(purpose),
    queryFn: async ({ signal }) => ({ items: list(await api.get("/admin/templates", { query: { purpose }, signal })).map(toTemplate) }),
    enabled: purpose === undefined || purpose !== "",
  });
}

/** `id` 는 템플릿 code 다 */
export function useSaveTemplate() {
  const client = useQueryClient();
  return useMutation<CourseTemplate, ApiError, { id?: string; input: Partial<CourseTemplateInput> }>({
    mutationFn: async ({ id, input }) =>
      toTemplate(id ? await api.patch<Raw>(`/admin/templates/${enc(id)}`, body(input, templateBody(input, false))) : await api.post<Raw>("/admin/templates", body(input, templateBody(input, true)))),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.templatesRoot }),
  });
}

/** API: {affinities: {태그: 값}}. 목: {items: [{tag, affinity}]} */
function toAffinities(raw: Raw): ItemList<TagAffinity> {
  if (Array.isArray(raw.items)) return raw as unknown as ItemList<TagAffinity>;
  const map = isRecord(raw.affinities) ? raw.affinities : {};
  return { items: Object.entries(map).flatMap(([tag, affinity]) => (typeof affinity === "number" ? [{ tag, affinity }] : [])) };
}

export function useTagAffinities(purpose: string | undefined) {
  return useQuery<ItemList<TagAffinity>, ApiError>({
    queryKey: adminKeys.affinities(purpose ?? ""),
    queryFn: async ({ signal }) => toAffinities(await api.get<Raw>(`/admin/purposes/${enc(purpose ?? "")}/tag-affinities`, { signal })),
    enabled: Boolean(purpose),
  });
}

export function useUpdateTagAffinities() {
  const client = useQueryClient();
  return useMutation<ItemList<TagAffinity>, ApiError, { purpose: string; items: TagAffinity[] }>({
    mutationFn: async ({ purpose, items }) =>
      toAffinities(await api.put<Raw>(`/admin/purposes/${enc(purpose)}/tag-affinities`, body({ items }, { affinities: Object.fromEntries(items.map((i) => [i.tag, i.affinity])) }))),
    onSuccess: (data, { purpose }) => client.setQueryData(adminKeys.affinities(purpose), data),
  });
}

// ── 수집 ────────────────────────────────────────────────────
function toJob(raw: Raw): IngestionJob {
  const status = str(raw.status, "queued") as IngestionJob["status"];
  return {
    id: String(raw.id), // API 는 정수 id
    region: str(raw.region),
    provider: str(raw.provider),
    status,
    progress: numOr(raw.progress, status === "succeeded" ? 1 : 0),
    collected: numOr(raw.collected, numOr(raw.fetched_count, 0)),
    created_count: numOrNull(raw.created_count) ?? undefined,
    updated_count: numOrNull(raw.updated_count) ?? undefined,
    failed_count: numOrNull(raw.failed_count) ?? undefined,
    job_type: strOrNull(raw.job_type) ?? undefined,
    started_at: strOrNull(raw.started_at),
    finished_at: strOrNull(raw.finished_at),
    error: strOrNull(raw.error),
  };
}

export function useIngestionJobs() {
  return useQuery<Page<IngestionJob>, ApiError>({
    queryKey: adminKeys.jobs,
    queryFn: async ({ signal }) => {
      const raw = await api.get<Raw>("/admin/ingestion/jobs", { query: { limit: 50 }, signal });
      return { items: list(raw).map(toJob), next_cursor: strOrNull(raw.next_cursor) };
    },
    refetchInterval: (query) => (query.state.data?.items.some((j) => j.status === "running" || j.status === "queued") ? (IS_MOCKING ? 3000 : 15_000) : false),
  });
}

export function useCreateIngestionJob() {
  const client = useQueryClient();
  return useMutation<IngestionJob, ApiError, { region: string; provider: string }>({
    mutationFn: async (input) => toJob(await api.post<Raw>("/admin/ingestion/jobs", input)),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.jobs }),
  });
}

export function useRetryIngestionJob() {
  const client = useQueryClient();
  return useMutation<IngestionJob, ApiError, string>({
    mutationFn: async (id) => toJob(await api.post<Raw>(`/admin/ingestion/jobs/${enc(id)}/retry`)),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.jobs });
      void client.invalidateQueries({ queryKey: adminKeys.regions });
    },
  });
}

// ── 분석 ────────────────────────────────────────────────────
/** 501 NOT_IMPLEMENTED — 고장이 아니라 "아직 없는 통계". 화면은 에러 대신 준비 중 상태를 보여준다 */
export const isNotReady = (error: ApiError | null | undefined): boolean => Boolean(error && (error.status === 501 || error.code === "NOT_IMPLEMENTED"));

export function useUserAnalytics(range: DateRange = {}) {
  return useQuery<UserAnalytics, ApiError>({
    queryKey: adminKeys.userAnalytics(range),
    queryFn: ({ signal }) => api.get("/admin/analytics/users", { query: { ...range }, signal }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    retry: (count, error) => !isNotReady(error) && error.retryable && count < 1,
  });
}

/** API `RecommendationStats` 는 평평하고 일별·분포 시계열이 없다 → 없는 것은 null */
function toRecAnalytics(raw: Raw, labels: AdminLabels): RecommendationAnalytics {
  if (isRecord(raw.totals)) return raw as unknown as RecommendationAnalytics; // 목
  const cells = (Array.isArray(raw.heatmap) ? (raw.heatmap as Raw[]) : []).map((c) => {
    const region = str(c.region);
    const purpose = str(c.purpose);
    return { region, region_name: region === "?" ? "지역 미상" : labels.region(region), purpose, purpose_name: purpose === "?" ? "목적 미상" : labels.purpose(purpose), count: numOr(c.count, 0) };
  });
  const byPurpose = new Map<string, { purpose: string; purpose_name: string; generated: number; save_rate: number | null }>();
  for (const c of cells) {
    const row = byPurpose.get(c.purpose) ?? { purpose: c.purpose, purpose_name: c.purpose_name, generated: 0, save_rate: null };
    row.generated += c.count;
    byPurpose.set(c.purpose, row);
  }
  return {
    range: { from: str(raw.date_from), to: str(raw.date_to) },
    totals: {
      generated: numOr(raw.generated, 0),
      save_rate: numOr(raw.save_rate, 0),
      reroll_rate: numOr(raw.reroll_rate, 0),
      swap_rate: null,
      avg_budget: numOrNull(raw.avg_budget_total),
      avg_budget_per_person: numOrNull(raw.avg_budget_per_person),
      avg_budget_utilization: null,
      slot_empty_rate: numOr(raw.slot_empty_rate, 0),
      p95_latency_ms: numOrNull(raw.latency_p95_ms),
      p50_latency_ms: numOrNull(raw.latency_p50_ms),
    },
    daily: null,
    by_purpose: [...byPurpose.values()].sort((a, b) => b.generated - a.generated),
    budget_histogram: null,
    heatmap: cells,
    latency: null,
  };
}

export function useRecommendationAnalytics(range: DateRange = {}) {
  const labels = useAdminLabels();
  return useQuery<Raw, ApiError, RecommendationAnalytics>({
    queryKey: adminKeys.recAnalytics(range),
    queryFn: ({ signal }) => api.get("/admin/analytics/recommendations", { query: { ...range }, signal }),
    select: useCallback((raw: Raw) => toRecAnalytics(raw, labels), [labels]),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

function toTopPlace(raw: Raw, labels: AdminLabels): TopPlace {
  return {
    id: str(raw.id),
    name: str(raw.name),
    region_name: strOrNull(raw.region_name) ?? labels.region(str(raw.region)),
    category_name: strOrNull(raw.category_name) ?? labels.category(str(raw.category)),
    impressions: numOr(raw.impressions, numOr(raw.recommend_count, 0)),
    saves: numOr(raw.saves, numOr(raw.save_count, 0)),
    swap_outs: numOrNull(raw.swap_outs),
  };
}

export function useTopPlaces() {
  const labels = useAdminLabels();
  return useQuery<Raw, ApiError, ItemList<TopPlace>>({
    queryKey: adminKeys.topPlaces,
    queryFn: ({ signal }) => api.get("/admin/analytics/places/top", { query: { limit: 10 }, signal }),
    select: useCallback((raw: Raw): ItemList<TopPlace> => ({ items: list(raw).map((p) => toTopPlace(p, labels)) }), [labels]),
    staleTime: 60_000,
  });
}

// ── 시스템 ──────────────────────────────────────────────────
const COMPONENT_LABEL: Record<string, string> = { database: "데이터베이스", cache: "캐시", search: "검색", llm: "AI 설명 (LLM)" };

/** API `Readiness`: {status: ready|degraded, components: {이름: {status: ok|down|disabled, backend}}} */
function toSystemHealth(raw: Raw): SystemHealth {
  if (Array.isArray(raw.services)) return raw as unknown as SystemHealth; // 목
  const components = isRecord(raw.components) ? raw.components : {};
  const status = str(raw.status);
  return {
    status: status === "ready" || status === "ok" ? "ok" : status === "degraded" ? "degraded" : "down",
    services: Object.entries(components).map(([name, value]) => {
      const c = isRecord(value) ? value : {};
      return { name: COMPONENT_LABEL[name] ?? name, status: str(c.status, "down") as SystemHealth["services"][number]["status"], latency_ms: null, backend: strOrNull(c.backend) };
    }),
    checked_at: new Date().toISOString(),
  };
}

export function useSystemHealth() {
  return useQuery<SystemHealth, ApiError>({
    queryKey: adminKeys.health,
    queryFn: async ({ signal }) => toSystemHealth(await api.get<Raw>("/admin/system/health", { signal })),
    refetchInterval: 30_000,
  });
}

/** `CacheInvalidateRequest.prefixes` — scope 를 안 주면 서버 기본값(지역·목적 목록, 코스, 후보)을 비운다 */
export function useInvalidateCache() {
  return useMutation<{ deleted: number }, ApiError, { scope?: string } | void>({
    mutationFn: async (input) => {
      const scope = input?.scope;
      const raw = await api.post<Raw | undefined>("/admin/cache/invalidate", IS_MOCKING ? (input ?? {}) : scope ? { prefixes: [scope] } : {});
      return { deleted: numOr(raw?.deleted, 0) };
    },
  });
}

export function useReindexSearch() {
  return useMutation<{ enqueued: number; search_backend: string | null }, ApiError, void>({
    mutationFn: async () => {
      const raw = await api.post<Raw | undefined>("/admin/search/reindex");
      return { enqueued: numOr(raw?.enqueued, 0), search_backend: strOrNull(raw?.search_backend) };
    },
  });
}

// ── DB 관리 (docs/50) ─────────────────────────────────────────
export interface DatabaseOverview {
  engine: "sqlite" | "postgresql";
  size_bytes: number | null;
  disk_free_bytes: number | null;
  tables: { name: string; label: string; rows: number }[];
  expired_unsaved_courses: number;
  unsaved_course_ttl_hours: number;
  visits_total: number;
  oldest_visit: string | null;
  backups: { name: string; size_bytes: number; created_at: string }[];
  backup_running: boolean;
}

export interface PurgeResult {
  matched: number;
  deleted: number;
  dry_run: boolean;
}

const databaseKey = ["admin", "database"] as const;

export function useDatabaseOverview() {
  return useQuery<DatabaseOverview, ApiError>({
    queryKey: databaseKey,
    queryFn: ({ signal }) => api.get("/admin/database", { signal }),
    // 백업이 도는 동안은 끝났는지 5초마다 본다
    refetchInterval: (q) => (q.state.data?.backup_running ? 5_000 : false),
  });
}

export function usePurgeCourses() {
  const client = useQueryClient();
  return useMutation<PurgeResult, ApiError, { dryRun: boolean }>({
    mutationFn: ({ dryRun }) => api.post(`/admin/database/purge-courses?dry_run=${dryRun}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: databaseKey }),
  });
}

export function usePurgeVisits() {
  const client = useQueryClient();
  return useMutation<PurgeResult, ApiError, { olderThanDays: number; dryRun: boolean }>({
    mutationFn: ({ olderThanDays, dryRun }) => api.post("/admin/database/purge-visits", { older_than_days: olderThanDays, dry_run: dryRun }),
    onSuccess: () => void client.invalidateQueries({ queryKey: databaseKey }),
  });
}

export function useStartBackup() {
  const client = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => api.post("/admin/database/backup"),
    onSuccess: () => void client.invalidateQueries({ queryKey: databaseKey }),
  });
}

export function useDeleteBackup() {
  const client = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (name) => api.delete(`/admin/database/backups/${enc(name)}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: databaseKey }),
  });
}

// ── 회원 · 방문 로그 · 코스 요청 (docs/50) ────────────────────
export type Who = "all" | "member" | "anonymous";
export interface UserRef {
  id: string;
  login_id: string | null;
  nickname: string | null;
}

export interface AdminMember {
  id: string;
  login_id: string | null;
  nickname: string | null;
  email: string | null;
  role: string;
  status: string;
  providers: string[];
  created_at: string;
  last_login_at: string | null;
  logins: number;
  courses_generated: number;
  courses_saved: number;
  last_ip: string | null;
  last_seen_at: string | null;
}

export interface AdminVisit {
  id: number;
  at: string;
  path: string;
  device: string;
  referrer: string | null;
  ip: string | null;
  visitor: string;
  user: UserRef | null;
}

export interface AdminCourseRequest {
  id: number;
  at: string;
  ip: string | null;
  user: UserRef | null;
  where: string;
  purpose: string;
  party_size: number | null;
  budget_total: number | null;
  start_at: string | null;
  taste: string[];
  latency_ms: number;
  candidates: number;
  warnings: string[];
  courses: { id: string; label: string; exists: boolean; status: string | null; total_price: number | null; places: string[] }[];
}

const MEMBERS_PAGE = 50;

export function useMembers(q: string, page: number) {
  return useQuery<{ items: AdminMember[]; total: number }, ApiError>({
    queryKey: ["admin", "members", q, page],
    queryFn: ({ signal }) => api.get("/admin/members", { query: { ...(q ? { q } : {}), limit: MEMBERS_PAGE, offset: page * MEMBERS_PAGE }, signal }),
    placeholderData: keepPreviousData,
  });
}
export { MEMBERS_PAGE };

export function useVisitLog(who: Who, q: string) {
  return useInfiniteQuery<{ items: AdminVisit[]; next_before: number | null }, ApiError>({
    queryKey: ["admin", "visits", who, q],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.get("/admin/visits", { query: { who, ...(q ? { q } : {}), limit: 100, ...(pageParam ? { before: pageParam as number } : {}) }, signal }),
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
}

export function useCourseRequests(who: Who) {
  return useInfiniteQuery<{ items: AdminCourseRequest[]; next_before: number | null }, ApiError>({
    queryKey: ["admin", "course-requests", who],
    initialPageParam: undefined as number | undefined,
    queryFn: ({ pageParam, signal }) =>
      api.get("/admin/course-requests", { query: { who, limit: 30, ...(pageParam ? { before: pageParam as number } : {}) }, signal }),
    getNextPageParam: (last) => last.next_before ?? undefined,
  });
}
