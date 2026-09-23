"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { getAccessToken, subscribeToken } from "@/lib/auth/token";
import { ApiError, api, newIdempotencyKey } from "./client";
import { safeJson, streamSse } from "./sse";
import { rememberCourseKey } from "@/lib/course-keys";
import type {
  CourseRoute,
  SuggestionList,
  Attraction,
  AttractionType,
  Banner,
  Category,
  ChatSession,
  Course,
  CourseDetail,
  EventItem,
  Features,
  FeedbackRequest,
  GenerateCourseRequest,
  GenerateCourseResponse,
  HotPlaces,
  ItemList,
  LocalSignature,
  Me,
  MePayload,
  OAuthProvider,
  AuthProviderStatus,
  Page,
  PerformanceList,
  PlaceDetail,
  Preferences,
  PreferencesPayload,
  ProblemDetails,
  Purpose,
  Region,
  ReorderRequest,
  SavedCourse,
  SavedCoursePayload,
  StayList,
  SwapRequest,
  Tag,
} from "./types";

const META_STALE = 10 * 60_000;

export const qk = {
  regions: (params?: { parent?: string; q?: string }) => ["meta", "regions", params ?? {}] as const,
  purposes: ["meta", "purposes"] as const,
  categories: ["meta", "categories"] as const,
  tags: (group?: string) => ["meta", "tags", group ?? "all"] as const,
  banners: (placement: string, region?: string) => ["meta", "banners", placement, region ?? null] as const,
  features: ["meta", "features"] as const,
  course: (id: string) => ["course", id] as const,
  myCourses: ["me", "courses"] as const,
  me: ["me"] as const,
  preferences: ["me", "preferences"] as const,
  attractions: (params: object) => ["attractions", params] as const,
  events: (params: object) => ["events", params] as const,
};

// ── 메타 ────────────────────────────────────────────────────
export function useRegions(params?: { parent?: string; q?: string }) {
  return useQuery<ItemList<Region>, ApiError>({
    queryKey: qk.regions(params),
    queryFn: ({ signal }) => api.get("/meta/regions", { query: params, signal }),
    staleTime: META_STALE,
    placeholderData: keepPreviousData,
  });
}

/**
 * API 의 `recommended_budget` 은 기준 인원 전체의 총액이고, 화면의 `budget_range` 는 1인당이다.
 * 둘을 섞어 쓰면 기본 예산이 인원수만큼 부풀려진다(데이트 2인 15만원) → API 가 주는 1인당 범위를 쓴다.
 */
type PurposeWire = Omit<Purpose, "budget_range"> & {
  budget_range?: Purpose["budget_range"];
  budget_per_person?: { min: number | null; max: number | null; typical?: number | null };
  recommended_budget?: { min: number | null; max: number | null };
};

function toPurpose({ recommended_budget, budget_per_person, ...p }: PurposeWire): Purpose {
  if (p.budget_range) return { ...p, budget_range: p.budget_range };
  const party = Math.max(1, p.default_party_size ?? 1);
  const min = budget_per_person?.min ?? Math.round((recommended_budget?.min ?? 0) / party);
  const max = budget_per_person?.max ?? Math.round((recommended_budget?.max ?? 0) / party);
  const typical = budget_per_person?.typical ?? undefined;
  return { ...p, budget_range: { min, max, ...(typical ? { typical } : {}) } };
}

/** context "university": 대학교를 고른 하루의 목적(캠퍼스 탐방 · 대학가 맛집 · 축제 즐기기 + 데이트 · 친구) — docs/34 */
export function usePurposes(context?: "university") {
  return useQuery<ItemList<Purpose>, ApiError>({
    queryKey: context ? [...qk.purposes, context] : qk.purposes,
    queryFn: async ({ signal }) => {
      const res = await api.get<ItemList<PurposeWire>>("/meta/purposes", { signal, ...(context ? { query: { context } } : {}) });
      return { ...res, items: res.items.map(toPurpose) };
    },
    staleTime: META_STALE,
  });
}

export function useCategories() {
  return useQuery<ItemList<Category>, ApiError>({
    queryKey: qk.categories,
    queryFn: ({ signal }) => api.get("/meta/categories", { signal }),
    staleTime: META_STALE,
  });
}

export function useTags(group?: string) {
  return useQuery<ItemList<Tag>, ApiError>({
    queryKey: qk.tags(group),
    queryFn: ({ signal }) => api.get("/meta/tags", { query: { group }, signal }),
    staleTime: META_STALE,
  });
}

export function useBanners(placement: string, region?: string) {
  return useQuery<ItemList<Banner>, ApiError>({
    queryKey: qk.banners(placement, region),
    queryFn: ({ signal }) => api.get("/meta/banners", { query: { placement, region }, signal }),
    staleTime: 60_000,
  });
}

/**
 * 이 환경에서 실제로 되는 기능. 화면은 안 되는 기능을 약속하지 않는다(예: LLM 키가 없으면 챗봇 입구를 접는다).
 * 아직 모를 때(data === undefined)는 입구를 숨기지도, 실패시키지도 말고 기다린다.
 * 옛 API(엔드포인트 없음)나 네트워크 오류면 "된다"로 두고 실제 호출의 오류 처리에 맡긴다.
 */
export function useFeatures() {
  return useQuery<Features, ApiError>({
    queryKey: qk.features,
    queryFn: async ({ signal }) => {
      try {
        return await api.get<Features>("/meta/features", { signal });
      } catch (error) {
        if (signal.aborted) throw error;
        return { chat: true };
      }
    },
    staleTime: META_STALE,
    retry: false,
  });
}

// ── 코스 ────────────────────────────────────────────────────
export function useGenerateCourse() {
  return useMutation<GenerateCourseResponse, ApiError, GenerateCourseRequest>({
    mutationFn: async (body) => {
      const res = await api.post<GenerateCourseResponse>("/courses/generate", body, { idempotencyKey: newIdempotencyKey(), timeoutMs: 30_000 });
      // 계정 없이 만든 코스는 이 브라우저만 고칠 수 있다: 편집 키를 기억한다 (docs/28)
      rememberCourseKey(res.courses.map((c) => c.id), res.edit_key);
      return res;
    },
  });
}

/** API 는 `{ course, og, request, siblings }` 봉투로 내려준다. 화면이 쓰는 평평한 CourseDetail 로 편다. */
type CourseDetailWire = Pick<CourseDetail, "request" | "siblings"> & {
  course: Course;
  og: { title: string; description: string; image?: string | null };
  nearby_events?: CourseDetail["nearby_events"];
  local?: CourseDetail["local"];
  /** 보는 사람 기준 (API 가 Authorization 헤더로 판단한다) */
  is_owner?: boolean;
  can_edit?: boolean;
  is_saved?: boolean;
};

function toCourseDetail(res: CourseDetail | CourseDetailWire): CourseDetail {
  if (!("course" in res)) return { ...res, can_edit: res.can_edit ?? true };
  const savedStatus = res.course.status === "saved" || res.course.status === "completed";
  return {
    ...res.course,
    request: res.request,
    siblings: res.siblings ?? [],
    nearby_events: res.nearby_events ?? [],
    local: res.local ?? null,
    // status 만 보면 친구가 저장한 코스도 "저장됨"으로 보인다 → 보는 사람 기준 값을 쓴다 (새로고침해도 유지)
    is_saved: res.is_saved ?? (res.can_edit === undefined && savedStatus),
    is_owner: res.is_owner ?? false,
    can_edit: res.can_edit ?? true,
    og: { title: res.og.title, description: res.og.description, image_url: res.og.image ?? null },
  };
}

const hasAccessToken = () => getAccessToken() !== null;
const noAccessToken = () => false;

export function useCourse(id: string) {
  const client = useQueryClient();
  // 상세 응답은 보는 사람에 따라 달라진다(is_owner·can_edit·is_saved) → 로그인 상태가 바뀌면 다시 받는다.
  // 새로고침 직후에는 세션 복원(refresh)이 끝나기 전에 비로그인으로 한 번 받기 때문에 꼭 필요하다.
  const signedIn = useSyncExternalStore(subscribeToken, hasAccessToken, noAccessToken);
  const seen = useRef(signedIn);
  useEffect(() => {
    if (seen.current === signedIn) return;
    seen.current = signedIn;
    void client.invalidateQueries({ queryKey: qk.course(id) });
  }, [client, id, signedIn]);

  return useQuery<CourseDetail, ApiError>({
    queryKey: qk.course(id),
    queryFn: async ({ signal }) => {
      const path = `/courses/${encodeURIComponent(id)}`;
      try {
        return toCourseDetail(await api.get<CourseDetail | CourseDetailWire>(path, { signal }));
      } catch (error) {
        // 공유 링크는 누구나 볼 수 있어야 한다: 세션이 죽어서(refresh 실패 → 토큰 비워짐) 난 401 이면 비로그인으로 다시 받는다
        if (error instanceof ApiError && error.status === 401 && !hasAccessToken()) {
          return toCourseDetail(await api.get<CourseDetail | CourseDetailWire>(path, { signal, retryOnUnauthorized: false }));
        }
        throw error;
      }
    },
    staleTime: 60_000,
    retry: (count, error) => error.retryable && count < 2,
  });
}

/** swap / reorder 응답(Course)을 상세 캐시에 덮어쓴다. request·siblings 등 상세 전용 필드는 유지. */
function mergeCourse(client: QueryClient, id: string, course: Course) {
  client.setQueryData<CourseDetail>(qk.course(id), (prev) => (prev ? { ...prev, ...course, id: prev.id } : prev));
}

export function useSwapStop(courseId: string) {
  const client = useQueryClient();
  return useMutation<Course, ApiError, SwapRequest>({
    mutationFn: (body) => api.post(`/courses/${encodeURIComponent(courseId)}/swap`, body),
    onSuccess: (course) => mergeCourse(client, courseId, course),
  });
}

/** 남은 돈으로 갈 만한 곳. 남은 돈이 바뀌면(바꾸기 · 넣기) 다시 묻는다 */
export function useSuggestions(courseId: string, budgetLeft: number) {
  return useQuery<SuggestionList, ApiError>({
    queryKey: ["course", courseId, "suggestions", budgetLeft],
    queryFn: ({ signal }) => api.get(`/courses/${encodeURIComponent(courseId)}/suggestions`, { signal }),
    enabled: budgetLeft > 0,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useAddStop(courseId: string) {
  const client = useQueryClient();
  return useMutation<Course, ApiError, { place_id: string }>({
    mutationFn: (body) => api.post(`/courses/${encodeURIComponent(courseId)}/stops`, body),
    onSuccess: (course) => mergeCourse(client, courseId, course),
  });
}

export function useReorderStops(courseId: string) {
  const client = useQueryClient();
  return useMutation<Course, ApiError, ReorderRequest>({
    mutationFn: (body) => api.post(`/courses/${encodeURIComponent(courseId)}/reorder`, body),
    onSuccess: (course) => mergeCourse(client, courseId, course),
  });
}

export function useSaveCourse(courseId: string) {
  const client = useQueryClient();
  return useMutation<{ id: string }, ApiError, void>({
    mutationFn: () => api.post(`/courses/${encodeURIComponent(courseId)}/save`),
    onSuccess: () => {
      client.setQueryData<CourseDetail>(qk.course(courseId), (prev) =>
        // 저장하면 주인 없는 코스도 내 것이 된다
        prev ? { ...prev, is_saved: true, is_owner: true, can_edit: true } : prev,
      );
      void client.invalidateQueries({ queryKey: qk.myCourses });
    },
  });
}

export function useCourseFeedback(courseId: string) {
  const client = useQueryClient();
  return useMutation<void, ApiError, FeedbackRequest>({
    mutationFn: (body) => api.post(`/courses/${encodeURIComponent(courseId)}/feedback`, body),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.myCourses }),
  });
}

export type NarrativeStatus = "idle" | "streaming" | "done" | "error";

/** GET /courses/{id}/narrative (SSE) — 코스 생성 응답과 분리된 LLM 설명 스트림 */
export function useCourseNarrative(courseId: string | undefined, enabled = true) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<NarrativeStatus>("idle");

  useEffect(() => {
    if (!courseId || !enabled) return;
    const controller = new AbortController();
    setText("");
    setStatus("streaming");
    streamSse(`/courses/${encodeURIComponent(courseId)}/narrative`, {
      signal: controller.signal,
      onMessage: ({ event, data }) => {
        if (event === "token") {
          const chunk = safeJson<{ text: string }>(data)?.text ?? data;
          setText((prev) => prev + chunk);
        } else if (event === "error") {
          setStatus("error");
        }
      },
    })
      .then(() => {
        if (!controller.signal.aborted) setStatus((s) => (s === "error" ? s : "done"));
      })
      .catch(() => {
        // 설명은 부가 정보다. 실패하면 조용히 summary 만 보여준다.
        if (!controller.signal.aborted) setStatus("error");
      });
    return () => controller.abort();
  }, [courseId, enabled]);

  return { text, status };
}

// ── 내 정보 ─────────────────────────────────────────────────
// API 응답 → 화면 모양. 목 핸들러는 화면 모양을, 실서버는 API 모양을 주므로 두 쪽을 다 받아 하나로 맞춘다.
// 빠진 값은 기본값으로 채운다: 옛 서버·부분 응답 때문에 화면이 죽는 일이 없어야 한다.
const OAUTH_PROVIDERS: readonly OAuthProvider[] = ["kakao", "naver", "google"];
const TRANSPORTS = ["walk", "transit", "car"] as const;
export const DEFAULT_NICKNAME = "짠이 친구";

export function toMe(raw: MePayload): Me {
  const provider = OAUTH_PROVIDERS.find((p) => p === raw.provider) ?? null;
  return {
    id: raw.id,
    nickname: raw.nickname?.trim() || DEFAULT_NICKNAME,
    email: raw.email ?? null,
    avatar_url: raw.avatar_url ?? null,
    role: raw.role,
    provider,
    created_at: raw.created_at,
  };
}

export function toPreferences(raw: PreferencesPayload): Preferences {
  const transport = raw.default_transport ?? raw.transport;
  return {
    liked_tags: Array.isArray(raw.liked_tags) ? raw.liked_tags : [],
    disliked_tags: Array.isArray(raw.disliked_tags) ? raw.disliked_tags : [],
    category_weights: raw.category_weights ?? {},
    transport: TRANSPORTS.find((t) => t === transport) ?? "walk",
  };
}

/** API 는 extra="forbid" 다 → 받는 네 필드만, API 이름(`default_transport`)으로 보낸다. */
export function toPreferencesPayload(prefs: Preferences): Required<Omit<PreferencesPayload, "transport">> {
  return {
    liked_tags: prefs.liked_tags,
    disliked_tags: prefs.disliked_tags,
    category_weights: prefs.category_weights ?? {},
    default_transport: prefs.transport,
  };
}

export function toSavedCourse(raw: SavedCoursePayload): SavedCourse {
  const label = raw.label?.trim() || "저장한 코스";
  return {
    id: raw.id,
    label,
    summary: raw.summary?.trim() || label,
    saved_at: raw.saved_at ?? raw.created_at ?? "",
    region_name: raw.region_name ?? null,
    purpose_name: raw.purpose_name ?? null,
    party_size: raw.party_size ?? 1,
    totals: {
      ...raw.totals,
      price: raw.totals?.price ?? raw.total_price ?? 0,
      duration_min: raw.totals?.duration_min ?? raw.duration_min ?? 0,
    },
    stop_names: Array.isArray(raw.stop_names) ? raw.stop_names.filter((n): n is string => typeof n === "string") : [],
    visited: raw.visited ?? raw.status === "completed",
    day: raw.day ?? null,
    days: raw.days ?? null,
  };
}

export function useMe(enabled = true) {
  return useQuery<Me, ApiError>({
    queryKey: qk.me,
    queryFn: async ({ signal }) => toMe(await api.get<MePayload>("/me", { signal })),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function useUpdateMe() {
  const client = useQueryClient();
  return useMutation<Me, ApiError, Partial<Pick<Me, "nickname">>>({
    mutationFn: async (body) => toMe(await api.patch<MePayload>("/me", body)),
    onSuccess: (me) => client.setQueryData(qk.me, me),
  });
}

const AUTH_PROVIDERS_KEY = ["auth", "providers"] as const;

/** 서버에 실제로 설정된 소셜 로그인만 누를 수 있게 한다 (설정 안 된 곳을 누르면 막다른 길이다). */
export function useAuthProviders(enabled = true) {
  return useQuery<ItemList<AuthProviderStatus>, ApiError>({
    queryKey: AUTH_PROVIDERS_KEY,
    queryFn: ({ signal }) => api.get("/auth/providers", { signal, retryOnUnauthorized: false }),
    enabled,
    staleTime: META_STALE,
    retry: false,
  });
}

export function useDeleteMe() {
  return useMutation<void, ApiError, void>({ mutationFn: () => api.delete("/me") });
}

export function usePreferences(enabled = true) {
  return useQuery<Preferences, ApiError>({
    queryKey: qk.preferences,
    queryFn: async ({ signal }) => toPreferences(await api.get<PreferencesPayload>("/me/preferences", { signal })),
    enabled,
    retry: false,
  });
}

export function useUpdatePreferences() {
  const client = useQueryClient();
  return useMutation<Preferences, ApiError, Preferences>({
    mutationFn: async (prefs) => toPreferences(await api.put<PreferencesPayload>("/me/preferences", toPreferencesPayload(prefs))),
    onSuccess: (prefs) => client.setQueryData(qk.preferences, prefs),
  });
}

export function useMyCourses(enabled = true) {
  return useInfiniteQuery<Page<SavedCourse>, ApiError>({
    queryKey: qk.myCourses,
    queryFn: async ({ pageParam, signal }) => {
      const page = await api.get<Partial<Page<SavedCoursePayload>>>("/me/courses", {
        query: { cursor: pageParam as string | undefined, limit: 20 },
        signal,
      });
      return { items: (page.items ?? []).map(toSavedCourse), next_cursor: page.next_cursor ?? null };
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled,
    retry: false,
  });
}

export function useDeleteMyCourse() {
  const client = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete(`/me/courses/${encodeURIComponent(id)}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.myCourses }),
  });
}

// ── 탐색 ────────────────────────────────────────────────────
export interface AttractionParams {
  region?: string;
  type?: AttractionType[];
  date?: string;
  q?: string;
}

/** API 의 AttractionItem / EventOut 은 화면 타입보다 필드가 적다. 없는 값은 빈 값으로 채워 카드가 안전하게 그리게 한다. */
type AttractionWire = Partial<Attraction> &
  Pick<Attraction, "id" | "type" | "name" | "lat" | "lng" | "is_free"> & {
    price?: number | null;
    starts_on?: string | null;
    ends_on?: string | null;
  };

function toAttraction(a: AttractionWire): Attraction {
  return {
    ...a,
    region: a.region ?? null,
    address: a.address ?? "",
    thumbnail_url: a.thumbnail_url ?? null,
    price_per_person: a.price_per_person ?? a.price ?? 0,
    period: a.period ?? (a.starts_on && a.ends_on ? { starts_on: a.starts_on, ends_on: a.ends_on } : null),
    tags: a.tags ?? [],
    summary: a.summary ?? "",
    rating: a.rating ?? null,
  };
}

type EventWire = Partial<EventItem> &
  Pick<EventItem, "id" | "title" | "starts_on" | "ends_on" | "is_free"> & {
    category?: string | null;
    address?: string | null;
    booking_url?: string | null;
  };

function toEventItem(e: EventWire): EventItem {
  return {
    ...e,
    type: e.type ?? e.category?.split(".").pop() ?? "festival",
    region: e.region ?? null,
    venue: e.venue ?? e.address ?? "",
    price: e.price ?? null,
    thumbnail_url: e.thumbnail_url ?? null,
    link_url: e.link_url ?? e.booking_url ?? null,
  };
}

export function useAttractions(params: AttractionParams) {
  return useInfiniteQuery<Page<Attraction>, ApiError>({
    queryKey: qk.attractions(params),
    queryFn: async ({ pageParam, signal }) => {
      const res = await api.get<Page<AttractionWire>>("/attractions", {
        query: { ...params, type: params.type, cursor: pageParam as string | undefined, limit: 24 },
        signal,
      });
      return { ...res, items: res.items.map(toAttraction) };
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useEvents(params: { region?: string; from?: string; to?: string }) {
  return useQuery<Page<EventItem>, ApiError>({
    queryKey: qk.events(params),
    queryFn: async ({ signal }) => {
      const res = await api.get<Page<EventWire>>("/events", { query: params, signal });
      return { ...res, items: res.items.map(toEventItem) };
    },
    placeholderData: keepPreviousData,
  });
}

// ── 길찾기 (지도 표시용) ─────────────────────────────────────
export interface WalkRoute {
  /** osrm = 실제 보행 경로, straight = 라우터가 응답하지 않아 직선으로 이은 폴백 */
  source: "osrm" | "straight";
  coordinates: [number, number][];
  /** coordinates: 이 구간만의 경로. 지도가 구간별로 색을 나눠 그릴 때 쓴다 */
  legs: { distance_m: number; duration_min: number; coordinates?: [number, number][] }[];
  distance_m: number;
  duration_min: number;
}

export interface AccessHint {
  subway: { station: string; exit: string | null; lat: number; lng: number; distance_m: number; walk_min: number } | null;
  bus: { name: string; stop_no: string | null; lat: number; lng: number; distance_m: number; walk_min: number } | null;
}

const pointsParam = (points: { lat: number; lng: number }[]) => points.map((p) => `${p.lat.toFixed(6)},${p.lng.toFixed(6)}`).join(";");

/** 방문 순서대로 이은 실제 보행 경로. 실패해도 화면은 직선으로 그리면 되므로 재시도하지 않는다. */
export function useWalkRoute(points: { lat: number; lng: number }[]) {
  const param = pointsParam(points);
  return useQuery<WalkRoute, ApiError>({
    queryKey: ["directions", "walk", param],
    queryFn: ({ signal }) => api.get("/directions/walk", { query: { points: param }, signal }),
    enabled: points.length >= 2,
    staleTime: 30 * 60_000,
    retry: false,
  });
}

/**
 * 코스의 실제 경로 (docs/27): 구간별 거리 · 시간 · 경로 좌표 + 이동 가능 여부 검증. 지도 · 카드 · 바텀시트가 이 하나를 읽는다.
 * 장소가 바뀌면(바꾸기 · 순서 변경) 키가 바뀌어 다시 계산한다. 실패해도 코스 화면은 엔진의 추정값으로 그대로 동작한다.
 */
export function useCourseRoute(courseId: string | undefined, placeIds: string[]) {
  return useQuery<CourseRoute, ApiError>({
    queryKey: ["course-route", courseId, placeIds.join(",")],
    queryFn: ({ signal }) => api.get(`/courses/${encodeURIComponent(courseId ?? "")}/route`, { signal }),
    enabled: Boolean(courseId) && placeIds.length >= 1,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

/** 지점별 가장 가까운 지하철 출구·버스 정류장 (OpenStreetMap 기반) */
export function useAccessHints(points: { lat: number; lng: number }[]) {
  const param = pointsParam(points);
  return useQuery<{ items: AccessHint[]; attribution: string }, ApiError>({
    queryKey: ["directions", "access", param],
    queryFn: ({ signal }) => api.get("/directions/access", { query: { points: param }, signal }),
    enabled: points.length >= 1,
    staleTime: 60 * 60_000,
    retry: false,
  });
}

export interface Station {
  name: string;
  lat: number;
  lng: number;
}

/** 역 이름 검색 — "신도림"·"반포"처럼 행정구역 이름이 아닌 동네를 역 주변으로 찾는다 */
export function useStations(q: string) {
  return useQuery<{ items: Station[] }, ApiError>({
    queryKey: ["directions", "stations", q],
    queryFn: ({ signal }) => api.get("/directions/stations", { query: { q, limit: 6 }, signal }),
    enabled: q.length >= 1,
    staleTime: 60 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/**
 * 위저드의 region 값은 문자열 하나다. 역을 고르면 "station:<이름>:<lat>,<lng>" 로 담아 두고,
 * 코스를 요청할 때 region 대신 origin 좌표로 풀어 보낸다(API 는 둘 중 하나를 받는다).
 */
export function encodeStation(s: Station): string {
  return `station:${s.name}:${s.lat.toFixed(6)},${s.lng.toFixed(6)}`;
}

export function decodeStation(value: string | undefined): Station | null {
  const m = /^station:([^:]+):(-?[\d.]+),(-?[\d.]+)$/.exec(value ?? "");
  return m ? { name: m[1]!, lat: Number(m[2]), lng: Number(m[3]) } : null;
}

export interface University {
  id: string;
  name: string;
  address: string | null;
  lat: number;
  lng: number;
}

/** 하루의 중심이 될 대학교 검색 (docs/34) — "가천", "홍익" */
export function useUniversities(q: string, enabled = true) {
  return useQuery<{ items: University[] }, ApiError>({
    queryKey: ["meta", "universities", q],
    queryFn: ({ signal }) => api.get("/meta/universities", { query: { ...(q ? { q } : {}), limit: 12 }, signal }),
    enabled,
    staleTime: 60 * 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/**
 * 대학교를 고르면 위저드의 region 값은 "campus:<id>:<이름>" — 코스를 요청할 때 anchor 로 풀어 보낸다.
 * 역("station:")과 같은 방식: 지역 트리에 없는 값이고, 지역 API(이름 · 핫플 · 명물)에 묻지 않는다.
 */
export function encodeCampus(u: Pick<University, "id" | "name">): string {
  return `campus:${u.id}:${u.name.replace(/:/g, " ")}`;
}

export function decodeCampus(value: string | undefined): { id: string; name: string } | null {
  const m = /^campus:([^:]+):(.+)$/.exec(value ?? "");
  return m ? { id: m[1]!, name: m[2]! } : null;
}

/** 지역 slug 가 아니라 한 지점(역 · 장소 · 캠퍼스)인 값: 지역 API 에 묻지 않는다 */
export function isPointValue(value: string | undefined): boolean {
  return Boolean(value && (value.startsWith("station:") || value.startsWith("campus:")));
}

/**
 * 둘러보기의 "이 근처로 코스 짜기" 링크. 장소도 역과 같은 값("station:<이름>:<lat>,<lng>")으로 담아
 * 위저드가 그 지점을 출발점(origin)으로 코스를 짠다. 이름의 ":" 는 구분자와 겹치므로 뺀다.
 */
export function planHrefNear(place: Station): string {
  const name = place.name.replace(/:/g, " ").replace(/\s+/g, " ").trim() || "여기";
  return `/plan?region=${encodeURIComponent(encodeStation({ ...place, name }))}`;
}

// ── 사진 (Wikimedia Commons 오픈 라이선스) ─────────────────────
export interface Photo {
  url: string;
  page_url: string | null;
  title: string;
  author: string;
  license: string;
}

/**
 * 업종 대표 이미지. 가게 실사진이 아니므로 화면에는 반드시 "예시"로 표시한다.
 * 실사진(카카오 로드뷰 · TourAPI · 점주/사용자 업로드)이 붙기 전까지의 임시 대체물이다.
 * 예시 사진을 아예 쓰지 않으려면 NEXT_PUBLIC_EXAMPLE_PHOTOS=off — 카드는 글자 타일로 돌아간다.
 */
export function useCategoryImages() {
  return useQuery<{ items: Record<string, Photo> }, ApiError>({
    queryKey: ["media", "categories"],
    queryFn: ({ signal }) => api.get("/media/categories", { signal }),
    enabled: process.env.NEXT_PUBLIC_EXAMPLE_PHOTOS !== "off",
    staleTime: 24 * 60 * 60_000,
    retry: false,
  });
}

/** "food.korean.bbq" → "food.korean" → "food" 순으로 가장 구체적인 이미지를 찾는다 */
export function categoryImageFor(images: Record<string, Photo> | undefined, category: string): Photo | undefined {
  if (!images) return undefined;
  const parts = category.split(".");
  while (parts.length > 0) {
    const hit = images[parts.join(".")];
    if (hit) return hit;
    parts.pop();
  }
  return undefined;
}

// ── 챗봇 ────────────────────────────────────────────────────
export function useCreateChatSession() {
  return useMutation<ChatSession, ApiError, void>({ mutationFn: () => api.post("/chat/sessions") });
}

export { ApiError };
export type { ProblemDetails };

/** 값이 바뀐 뒤 delay ms 동안 조용하면 반영한다 (검색 입력용). */
export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** 지역 하나. 동 · 읍 · 면은 전체 목록에 없다(1,400곳) → 고른 뒤의 이름은 여기서 읽는다. */
export function useRegion(slug: string | undefined, enabled = true) {
  return useQuery<Region, ApiError>({
    queryKey: ["meta", "region", slug],
    queryFn: ({ signal }) => api.get(`/meta/regions/${encodeURIComponent(slug ?? "")}`, { signal }),
    enabled: enabled && Boolean(slug) && !isPointValue(slug),
    staleTime: META_STALE,
    retry: false,
  });
}

/** 고른 지역: 전체 목록에 있으면 거기서, 없으면(동) 한 건을 물어서. 아직 모르면 undefined. */
export function usePickedRegion(slug: string | undefined): Region | undefined {
  const regions = useRegions();
  const listed = regions.data?.items.find((r) => r.slug === slug);
  const one = useRegion(slug, regions.isSuccess && !listed);
  return listed ?? one.data;
}

export function useRegionName(slug: string | undefined): string | undefined {
  return usePickedRegion(slug)?.name;
}

/** 이 지역에서 사람들이 실제로 많이 가는 곳 (티맵 내비게이션 실측). 모르는 동네를 고를 때의 길잡이. */
export function useHotPlaces(regionSlug: string | undefined, limit = 8) {
  return useQuery<HotPlaces, ApiError>({
    queryKey: ["meta", "hot", regionSlug, limit],
    queryFn: ({ signal }) => api.get(`/meta/regions/${encodeURIComponent(regionSlug ?? "")}/hot`, { query: { limit }, signal }),
    enabled: Boolean(regionSlug) && !isPointValue(regionSlug),
    staleTime: 60 * 60_000,
    retry: false,
  });
}

/** 이 동네가 무엇으로 알려져 있는지 (명물 · 보러 오는 곳). 위저드가 지역을 고른 직후에 보여 준다. */
export function useLocalSignature(regionSlug: string | undefined) {
  return useQuery<LocalSignature, ApiError>({
    queryKey: ["meta", "signature", regionSlug],
    queryFn: ({ signal }) => api.get(`/meta/regions/${encodeURIComponent(regionSlug ?? "")}/signature`, { signal }),
    enabled: Boolean(regionSlug) && !isPointValue(regionSlug),
    staleTime: 60 * 60_000,
    retry: false,
  });
}

/** 이 지점 근처의 숙소 (관광공사 등재분). 가까이에 없으면 반경을 넓혀 다시 찾는다 — 등재 숙소는 전국 3천 곳뿐이다. */
export function useStays(at: { lat: number; lng: number } | null) {
  return useQuery<StayList, ApiError>({
    queryKey: ["stays", at?.lat.toFixed(4), at?.lng.toFixed(4)],
    queryFn: async ({ signal }) => {
      const query = { lat: at!.lat, lng: at!.lng, limit: 6 };
      const near = await api.get<StayList>("/stays", { query: { ...query, radius_m: 3000 }, signal });
      return near.items.length >= 3 ? near : api.get<StayList>("/stays", { query: { ...query, radius_m: 12000 }, signal });
    },
    enabled: at !== null,
    staleTime: 60 * 60_000,
    retry: false,
  });
}

const MAX_PARTIAL_REFETCH = 6;

/** 고른 시간대에 근처에서 실제로 하는 공연. 키가 없는 환경이면 부르지 않는다(useFeatures().performances). */
export function usePerformances(params: { lat: number; lng: number; start_at: string; duration_min: number } | null) {
  return useQuery<PerformanceList, ApiError>({
    queryKey: ["performances", params],
    queryFn: ({ signal }) => api.get("/performances", { query: { ...params!, radius_m: 4000 }, signal, timeoutMs: 25_000 }),
    enabled: params !== null,
    staleTime: 30 * 60_000,
    retry: false,
    // 큰 도시는 한 번에 다 확인하지 못한다(partial). 받은 만큼 먼저 보여 주고, 서버 캐시가 채워지는 동안 몇 번 더 받아 온다.
    refetchInterval: (query) => (query.state.data?.partial && query.state.dataUpdateCount < MAX_PARTIAL_REFETCH ? 4_000 : false),
  });
}

/** 장소 상세. 시트를 열 때만 부른다. */
export function usePlaceDetail(id: string | null) {
  return useQuery<PlaceDetail, ApiError>({
    queryKey: ["place", id],
    queryFn: ({ signal }) => api.get(`/places/${encodeURIComponent(id ?? "")}`, { signal }),
    enabled: id !== null,
    staleTime: 30 * 60_000,
    retry: false,
  });
}
