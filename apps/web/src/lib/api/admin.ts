"use client";

/**
 * 관리자 API 훅 — docs/03-api-spec.md §7.
 * 전부 `/admin/*` 이고 서버에서 role ∈ {admin, operator} 를 검증한다. 화면은 403 을 짠이 에러 상태로 보여준다.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ApiError, api, newIdempotencyKey } from "./client";
import type {
  AdminBanner,
  AdminBannerInput,
  AdminEvent,
  AdminEventInput,
  AdminPlace,
  AdminPlaceInput,
  AdminRegion,
  AdminRegionInput,
  CourseTemplate,
  IngestionJob,
  ItemList,
  Page,
  PlaceRevision,
  PlaceStatus,
  RecommendationAnalytics,
  ScoringProfile,
  ScoreBreakdown,
  SystemHealth,
  TopPlace,
  UserAnalytics,
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

export interface ImportResult {
  job_id: string;
  accepted: number;
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

// ── 장소 승인 · 수정 ────────────────────────────────────────
export function useAdminPlaces(params: AdminPlaceListParams) {
  return useQuery<AdminPlacePage, ApiError>({
    queryKey: adminKeys.places(params),
    queryFn: ({ signal }) => api.get("/admin/places", { query: { ...params }, signal }),
    placeholderData: keepPreviousData,
  });
}

export function usePlaceRevisions(id: string | undefined) {
  return useQuery<ItemList<PlaceRevision>, ApiError>({
    queryKey: adminKeys.revisions(id ?? ""),
    queryFn: ({ signal }) => api.get(`/admin/places/${enc(id ?? "")}/revisions`, { signal }),
    enabled: Boolean(id),
  });
}

function useInvalidatePlaces() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: adminKeys.placesRoot });
}

export function useApprovePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, string>({
    mutationFn: (id) => api.post(`/admin/places/${enc(id)}/approve`),
    onSuccess: () => void invalidate(),
  });
}

export function useRejectPlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, { id: string; reason?: string }>({
    mutationFn: ({ id, reason }) => api.post(`/admin/places/${enc(id)}/reject`, { reason }),
    onSuccess: () => void invalidate(),
  });
}

export function useBulkApprovePlaces() {
  const invalidate = useInvalidatePlaces();
  return useMutation<BulkApproveResult, ApiError, string[]>({
    mutationFn: (ids) => api.post("/admin/places/bulk-approve", { ids }),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdatePlace() {
  const client = useQueryClient();
  return useMutation<AdminPlace, ApiError, { id: string; input: AdminPlaceInput }>({
    mutationFn: ({ id, input }) => api.patch(`/admin/places/${enc(id)}`, input),
    onSuccess: (_place, { id }) => {
      void client.invalidateQueries({ queryKey: adminKeys.placesRoot });
      void client.invalidateQueries({ queryKey: adminKeys.revisions(id) });
    },
  });
}

export function useMergePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, { id: string; into: string }>({
    mutationFn: ({ id, into }) => api.post(`/admin/places/${enc(id)}/merge`, { into }),
    onSuccess: () => void invalidate(),
  });
}

/** 관광지·문화공간 직접 추가 (category 의 course_role = ATTRACTION / CULTURE) */
export function useCreatePlace() {
  const invalidate = useInvalidatePlaces();
  return useMutation<AdminPlace, ApiError, AdminPlaceInput>({
    mutationFn: (input) => api.post("/admin/places", input, { idempotencyKey: newIdempotencyKey() }),
    onSuccess: () => void invalidate(),
  });
}

/** CSV/JSON 업로드 → `file` provider 수집 잡 */
export function useImportPlaces() {
  const client = useQueryClient();
  return useMutation<ImportResult, ApiError, { file: File; region?: string }>({
    mutationFn: ({ file, region }) => {
      const form = new FormData();
      form.append("file", file);
      if (region) form.append("region", region);
      return api.post("/admin/places/import", form, { timeoutMs: 60_000 });
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.jobs }),
  });
}

// ── 이벤트 ──────────────────────────────────────────────────
export function useAdminEvents() {
  return useQuery<Page<AdminEvent>, ApiError>({
    queryKey: adminKeys.events,
    queryFn: ({ signal }) => api.get("/admin/events", { query: { limit: 100 }, signal }),
  });
}

export function useSaveEvent() {
  const client = useQueryClient();
  return useMutation<AdminEvent, ApiError, { id?: string; input: AdminEventInput }>({
    mutationFn: ({ id, input }) => (id ? api.patch(`/admin/events/${enc(id)}`, input) : api.post("/admin/events", input)),
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
export function useAdminBanners() {
  return useQuery<Page<AdminBanner>, ApiError>({
    queryKey: adminKeys.banners,
    queryFn: ({ signal }) => api.get("/admin/banners", { query: { limit: 100 }, signal }),
  });
}

export function useSaveBanner() {
  const client = useQueryClient();
  return useMutation<AdminBanner, ApiError, { id?: string; input: Partial<AdminBannerInput> }>({
    mutationFn: ({ id, input }) => (id ? api.patch(`/admin/banners/${enc(id)}`, input) : api.post("/admin/banners", input)),
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

export function usePresignUpload() {
  return useMutation<PresignResult, ApiError, { filename: string; content_type: string }>({
    mutationFn: (body) => api.post("/admin/uploads/presign", body),
  });
}

// ── 지역 ────────────────────────────────────────────────────
export function useAdminRegions() {
  return useQuery<ItemList<AdminRegion>, ApiError>({
    queryKey: adminKeys.regions,
    queryFn: ({ signal }) => api.get("/admin/regions", { signal }),
    // 수집 중인 지역이 있으면 3초마다 상태를 다시 읽는다
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === "collecting") ? 3000 : false),
  });
}

function useInvalidateRegions() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: adminKeys.regions });
    void client.invalidateQueries({ queryKey: ["meta", "regions"] });
  };
}

export function useCreateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, AdminRegionInput>({
    mutationFn: (input) => api.post("/admin/regions", input),
    onSuccess: invalidate,
  });
}

export function useUpdateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, { slug: string; input: AdminRegionPatch }>({
    mutationFn: ({ slug, input }) => api.patch(`/admin/regions/${enc(slug)}`, input),
    onSuccess: invalidate,
  });
}

export function useCollectRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<IngestionJob, ApiError, string>({
    mutationFn: (slug) => api.post(`/admin/regions/${enc(slug)}/collect`),
    onSuccess: invalidate,
  });
}

export function useActivateRegion() {
  const invalidate = useInvalidateRegions();
  return useMutation<AdminRegion, ApiError, string>({
    mutationFn: (slug) => api.post(`/admin/regions/${enc(slug)}/activate`),
    onSuccess: invalidate,
  });
}

// ── 추천 설정 ───────────────────────────────────────────────
export function useScoringProfile(purpose: string | undefined) {
  return useQuery<ScoringProfile, ApiError>({
    queryKey: adminKeys.scoring(purpose ?? ""),
    queryFn: ({ signal }) => api.get(`/admin/scoring-profiles/${enc(purpose ?? "")}`, { signal }),
    enabled: Boolean(purpose),
  });
}

export function useUpdateScoringProfile() {
  const client = useQueryClient();
  return useMutation<
    ScoringProfile,
    ApiError,
    { purpose: string; weights: ScoreBreakdown; params?: Record<string, unknown> }
  >({
    mutationFn: ({ purpose, ...body }) => api.put(`/admin/scoring-profiles/${enc(purpose)}`, body),
    onSuccess: (profile) => client.setQueryData(adminKeys.scoring(profile.purpose), profile),
  });
}

export function useTemplates(purpose?: string) {
  return useQuery<ItemList<CourseTemplate>, ApiError>({
    queryKey: adminKeys.templates(purpose),
    queryFn: ({ signal }) => api.get("/admin/templates", { query: { purpose }, signal }),
    enabled: purpose === undefined || purpose !== "",
  });
}

export function useSaveTemplate() {
  const client = useQueryClient();
  return useMutation<CourseTemplate, ApiError, { id?: string; input: Partial<CourseTemplateInput> }>({
    mutationFn: ({ id, input }) =>
      id ? api.patch(`/admin/templates/${enc(id)}`, input) : api.post("/admin/templates", input),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.templatesRoot }),
  });
}

export function useTagAffinities(purpose: string | undefined) {
  return useQuery<ItemList<TagAffinity>, ApiError>({
    queryKey: adminKeys.affinities(purpose ?? ""),
    queryFn: ({ signal }) => api.get(`/admin/purposes/${enc(purpose ?? "")}/tag-affinities`, { signal }),
    enabled: Boolean(purpose),
  });
}

export function useUpdateTagAffinities() {
  const client = useQueryClient();
  return useMutation<ItemList<TagAffinity>, ApiError, { purpose: string; items: TagAffinity[] }>({
    mutationFn: ({ purpose, items }) => api.put(`/admin/purposes/${enc(purpose)}/tag-affinities`, { items }),
    onSuccess: (data, { purpose }) => client.setQueryData(adminKeys.affinities(purpose), data),
  });
}

// ── 수집 ────────────────────────────────────────────────────
export function useIngestionJobs() {
  return useQuery<Page<IngestionJob>, ApiError>({
    queryKey: adminKeys.jobs,
    queryFn: ({ signal }) => api.get("/admin/ingestion/jobs", { query: { limit: 20 }, signal }),
    refetchInterval: (query) =>
      query.state.data?.items.some((j) => j.status === "running" || j.status === "queued") ? 3000 : false,
  });
}

export function useCreateIngestionJob() {
  const client = useQueryClient();
  return useMutation<IngestionJob, ApiError, { region: string; provider: string }>({
    mutationFn: (body) => api.post("/admin/ingestion/jobs", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.jobs }),
  });
}

export function useRetryIngestionJob() {
  const client = useQueryClient();
  return useMutation<IngestionJob, ApiError, string>({
    mutationFn: (id) => api.post(`/admin/ingestion/jobs/${enc(id)}/retry`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: adminKeys.jobs });
      void client.invalidateQueries({ queryKey: adminKeys.regions });
    },
  });
}

// ── 분석 ────────────────────────────────────────────────────
export function useUserAnalytics(range: DateRange = {}) {
  return useQuery<UserAnalytics, ApiError>({
    queryKey: adminKeys.userAnalytics(range),
    queryFn: ({ signal }) => api.get("/admin/analytics/users", { query: { ...range }, signal }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useRecommendationAnalytics(range: DateRange = {}) {
  return useQuery<RecommendationAnalytics, ApiError>({
    queryKey: adminKeys.recAnalytics(range),
    queryFn: ({ signal }) => api.get("/admin/analytics/recommendations", { query: { ...range }, signal }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useTopPlaces() {
  return useQuery<ItemList<TopPlace>, ApiError>({
    queryKey: adminKeys.topPlaces,
    queryFn: ({ signal }) => api.get("/admin/analytics/places/top", { query: { limit: 10 }, signal }),
    staleTime: 60_000,
  });
}

// ── 시스템 ──────────────────────────────────────────────────
export function useSystemHealth() {
  return useQuery<SystemHealth, ApiError>({
    queryKey: adminKeys.health,
    queryFn: ({ signal }) => api.get("/admin/system/health", { signal }),
    refetchInterval: 30_000,
  });
}

export function useInvalidateCache() {
  return useMutation<void, ApiError, { scope?: string } | void>({
    mutationFn: (body) => api.post("/admin/cache/invalidate", body ?? {}),
  });
}

export function useReindexSearch() {
  return useMutation<void, ApiError, void>({
    mutationFn: () => api.post("/admin/search/reindex"),
  });
}
