/**
 * ⚠️ 개발용 관리자 목 데이터 (in-memory, 새로고침하면 초기화).
 * 화면 컴포넌트는 이 파일을 import 하지 않는다 — MSW 핸들러 전용.
 */
import type {
  AdminBanner,
  AdminEvent,
  AdminPlace,
  AdminRegion,
  CourseTemplate,
  IngestionJob,
  PlaceRevision,
  RecommendationAnalytics,
  ScoreBreakdown,
  ScoringProfile,
  SystemHealth,
  TopPlace,
  UserAnalytics,
} from "@/lib/api/types";
import { purposes, regions } from "./meta";

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

const DAY = 86_400_000;
export const isoAgo = (ms: number) => new Date(Date.now() - ms).toISOString();
export const dayOffset = (offset: number) => new Date(Date.now() + offset * DAY).toISOString().slice(0, 10);

// ── 장소 ────────────────────────────────────────────────────
interface PlaceSeed {
  name: string;
  rawName: string;
  category: string;
  category_name: string;
  role: AdminPlace["course_role"];
  price: number | null;
  rawPrice: string;
  tags: string[];
  source: string;
}

const PLACE_SEEDS: PlaceSeed[] = [
  { name: "연남 덮밥집", rawName: "연남덮밥집 본점", category: "food.japanese", category_name: "일식", role: "MEAL", price: 12000, rawPrice: "12,000원~", tags: ["가성비", "조용한"], source: "kakao_local" },
  { name: "손칼국수 한그릇", rawName: "손칼국수한그릇", category: "food.korean", category_name: "한식", role: "MEAL", price: 9000, rawPrice: "9000", tags: ["가성비", "한식"], source: "naver_place" },
  { name: "카페 책과밤", rawName: "책과밤 (북카페)", category: "cafe.dessert", category_name: "디저트", role: "CAFE", price: 6000, rawPrice: "아메리카노 5,500 / 케이크 6,500", tags: ["조용한", "아늑한"], source: "kakao_local" },
  { name: "루프탑 무드", rawName: "ROOFTOP MOOD", category: "cafe.coffee", category_name: "커피", role: "CAFE", price: 11000, rawPrice: "11000", tags: ["뷰맛집"], source: "naver_place" },
  { name: "숲길 산책", rawName: "경의선숲길공원", category: "play.park", category_name: "공원·산책", role: "ATTRACTION", price: 0, rawPrice: "무료", tags: ["산책"], source: "tour_api" },
  { name: "동네 미술관 기획전", rawName: "동네미술관", category: "culture.exhibition", category_name: "전시", role: "CULTURE", price: 5000, rawPrice: "성인 5,000원", tags: ["전시", "실내"], source: "tour_api" },
  { name: "와인바 밤결", rawName: "밤결 와인바", category: "bar", category_name: "술집", role: "BAR", price: 18000, rawPrice: "글라스 18,000~", tags: ["조용한"], source: "user_suggest" },
  { name: "보드게임 라운지", rawName: "보드게임라운지 2호점", category: "play.game", category_name: "오락·포토", role: "ATTRACTION", price: 6000, rawPrice: "1인 6000원(2시간)", tags: ["실내"], source: "kakao_local" },
];

const STATUSES: AdminPlace["status"][] = ["pending", "pending", "pending", "approved", "pending", "approved", "rejected", "pending"];

export const places: AdminPlace[] = regions.slice(0, 4).flatMap((region, ri) =>
  PLACE_SEEDS.map((seed, si): AdminPlace => {
    const id = `ap_${ri}_${si}`;
    const lat = Number((region.center.lat + (hash(id) - 0.5) * 0.012).toFixed(6));
    const lng = Number((region.center.lng + (hash(`${id}x`) - 0.5) * 0.012).toFixed(6));
    const address = `${region.parent?.name ?? ""} ${region.name} ${Math.round(hash(`${id}a`) * 60) + 1}길 ${Math.round(hash(`${id}b`) * 30) + 1}`.trim();
    const status = STATUSES[(si + ri) % STATUSES.length] ?? "pending";
    return {
      id,
      name: seed.name,
      status,
      category: seed.category,
      category_name: seed.category_name,
      course_role: seed.role,
      region: { slug: region.slug, name: region.name },
      address,
      lat,
      lng,
      price_per_person: seed.price,
      is_free: seed.price === 0,
      rating: Number((4 + hash(`${id}r`) * 0.8).toFixed(1)),
      review_count: Math.round(hash(`${id}v`) * 1500) + 12,
      tags: seed.tags,
      source: seed.source,
      created_at: isoAgo((si + ri * 3 + 1) * 5 * 3_600_000),
      updated_at: isoAgo((si + ri) * 3_600_000),
      source_raw: {
        place_name: seed.rawName,
        category_name: `${seed.category_name} > 기타`,
        road_address_name: `${address} 1층`,
        x: String(lng),
        y: String(lat),
        price_text: seed.rawPrice,
        phone: `02-${300 + si}-${1000 + ri * 37}`,
        tags_text: seed.tags.join("/"),
      },
      normalized: {
        place_name: seed.name,
        category_name: seed.category_name,
        road_address_name: address,
        x: String(lng),
        y: String(lat),
        price_text: seed.price === null ? null : String(seed.price),
        phone: `02-${300 + si}-${1000 + ri * 37}`,
        tags_text: seed.tags.join("/"),
      },
      duplicate_of: si === 3 && ri === 1 ? { id: "ap_0_3", name: "루프탑 무드" } : null,
    };
  }),
);

export const revisions = new Map<string, PlaceRevision[]>();

// ── 지역 ────────────────────────────────────────────────────
export const adminRegions: AdminRegion[] = regions.map((r, i) => ({
  slug: r.slug,
  name: r.name,
  parent: r.parent?.slug ?? null,
  level: r.level,
  center: r.center,
  radius_m: r.radius_m,
  keywords: [r.name, `${r.name} 맛집`, `${r.name} 카페`],
  status: i === regions.length - 1 ? "ready" : "active",
  place_count: r.place_count,
  pending_count: Math.round(hash(r.slug) * 40),
  last_collected_at: isoAgo((i + 1) * DAY),
  last_job: { id: `job_seed_${i}`, status: "succeeded", progress: 1 },
}));

export const jobs: IngestionJob[] = adminRegions.slice(0, 5).map((r, i) => ({
  id: `job_seed_${i}`,
  region: r.slug,
  provider: i % 2 === 0 ? "kakao_local" : "tour_api",
  status: "succeeded",
  progress: 1,
  collected: r.place_count,
  started_at: isoAgo((i + 1) * DAY + 1_800_000),
  finished_at: isoAgo((i + 1) * DAY),
  error: null,
}));

/** 목 수집 잡은 시작 후 이 시간이 지나면 끝난 것으로 본다 */
export const COLLECT_DURATION_MS = 12_000;
export const collectStartedAt = new Map<string, number>();

// ── 이벤트 · 배너 ───────────────────────────────────────────
export const events: AdminEvent[] = regions.slice(0, 4).map((r, i) => ({
  id: `ev_${i}`,
  title: [`${r.name} 가을 거리축제`, "플리마켓 & 버스킹 위크", "미디어아트 특별전", "야시장 페스타"][i] ?? "행사",
  type: ["festival", "market", "exhibition", "festival"][i] ?? "festival",
  region: r.slug,
  region_name: r.name,
  venue: `${r.name} 일대`,
  starts_on: dayOffset(-3 + i * 2),
  ends_on: dayOffset(6 + i * 5),
  is_free: i !== 2,
  price: i === 2 ? 15000 : null,
  link_url: null,
  status: i === 3 ? "draft" : "published",
}));

export const banners: AdminBanner[] = [
  { id: "b_autumn", title: "가을 축제 모아보기", subtitle: "이번 주말, 무료로 즐기는 동네 축제", image_url: null, link_url: "/explore?type=festival", placement: "home", region: null, starts_at: isoAgo(5 * DAY), ends_at: new Date(Date.now() + 20 * DAY).toISOString(), is_active: true, impressions: 18240, clicks: 1312 },
  { id: "b_chat", title: "말로 하면 짠이가 짜줘요", subtitle: "짠이 챗봇 써보기", image_url: null, link_url: "/chat", placement: "home", region: null, starts_at: isoAgo(12 * DAY), ends_at: new Date(Date.now() + 40 * DAY).toISOString(), is_active: true, impressions: 9420, clicks: 511 },
  { id: "b_seongsu", title: "성수 팝업 지도", subtitle: null, image_url: null, link_url: "/explore?region=seoul-seongsu", placement: "explore", region: "seoul-seongsu", starts_at: isoAgo(30 * DAY), ends_at: isoAgo(2 * DAY), is_active: false, impressions: 30110, clicks: 2044 },
];

// ── 추천 설정 ───────────────────────────────────────────────
const BASE_WEIGHTS: ScoreBreakdown = { budget: 0.24, distance: 0.12, rating: 0.16, sentiment: 0.14, congestion: 0.08, time_fit: 0.08, preference: 0.12, purpose_fit: 0.06, curated: 0, buzz: 0 };

const WEIGHT_TWEAKS: Record<string, Partial<ScoreBreakdown>> = {
  date: { sentiment: 0.16, rating: 0.14 },
  solo: { budget: 0.28, congestion: 0.1, sentiment: 0.12, purpose_fit: 0.04, rating: 0.14 },
  family: { distance: 0.14, purpose_fit: 0.08, budget: 0.22, congestion: 0.06 },
};

export const scoringProfiles = new Map<string, ScoringProfile>(
  purposes.map((p, i) => [
    p.code,
    {
      purpose: p.code,
      version: 3 - (i % 2),
      weights: { ...BASE_WEIGHTS, ...(WEIGHT_TWEAKS[p.code] ?? {}) },
      params: { u_star: 0.85, sigma: 0.18, lambda_t: 0.015, lambda_o: 2.0, diversity: 0.05 },
      experiment_key: i === 0 ? "date-mood-boost" : null,
      updated_at: isoAgo((i + 2) * DAY),
      updated_by: "operator@naegajjanday.com",
    },
  ]),
);

const TEMPLATE_SLOTS: Record<string, CourseTemplate["slots"]> = {
  date: [
    { role: "MEAL", budget_share: 0.55, stay_min: 60, is_optional: false, is_order_flexible: false },
    { role: "CAFE", budget_share: 0.2, stay_min: 50, is_optional: false, is_order_flexible: false },
    { role: "ATTRACTION", budget_share: 0.05, stay_min: 40, is_optional: false, is_order_flexible: true },
    { role: "BAR", budget_share: 0.2, stay_min: 70, is_optional: true, is_order_flexible: false },
  ],
  travel: [
    { role: "ATTRACTION", budget_share: 0.1, stay_min: 60, is_optional: false, is_order_flexible: true },
    { role: "MEAL", budget_share: 0.5, stay_min: 60, is_optional: false, is_order_flexible: false },
    { role: "CULTURE", budget_share: 0.2, stay_min: 70, is_optional: false, is_order_flexible: true },
    { role: "CAFE", budget_share: 0.2, stay_min: 50, is_optional: true, is_order_flexible: false },
  ],
};
const DEFAULT_SLOTS: CourseTemplate["slots"] = [
  { role: "MEAL", budget_share: 0.6, stay_min: 60, is_optional: false, is_order_flexible: false },
  { role: "CAFE", budget_share: 0.25, stay_min: 50, is_optional: false, is_order_flexible: false },
  { role: "ATTRACTION", budget_share: 0.15, stay_min: 50, is_optional: true, is_order_flexible: true },
];

export const templates: CourseTemplate[] = purposes.flatMap((p) =>
  (["lunch", "evening"] as const).map((band, bi): CourseTemplate => ({
    id: `tpl_${p.code}_${band}`,
    name: `${p.name} · ${band === "lunch" ? "점심" : "저녁"}`,
    purpose: p.code,
    time_band: band,
    min_budget_per_person: p.budget_range.min,
    party_size_min: 1,
    party_size_max: p.max_party_size ?? 8,
    slots: (TEMPLATE_SLOTS[p.code] ?? DEFAULT_SLOTS).map((s) => ({ ...s })),
    is_active: bi === 1 || p.code !== "solo",
  })),
);

export const tagAffinities = new Map<string, { tag: string; affinity: number }[]>();

// ── 분석 ────────────────────────────────────────────────────
function series<T>(days: number, make: (date: string, i: number) => T): T[] {
  return Array.from({ length: days }, (_, i) => make(dayOffset(i - days + 1), i));
}

export function userAnalytics(): UserAnalytics {
  const daily = series(30, (date, i) => {
    const weekend = [0, 6].includes(new Date(date).getDay()) ? 1.35 : 1;
    const dau = Math.round((820 + i * 14 + hash(`d${date}`) * 160) * weekend);
    const logged_in = Math.round(dau * 0.3);
    const courses = Math.round(dau * 0.4);
    return {
      date,
      dau,
      visitors: dau,
      logged_in,
      anonymous: dau - logged_in,
      page_views: dau * 4,
      new_users: Math.round(dau * (0.11 + hash(`n${date}`) * 0.05)),
      logins: logged_in,
      courses,
      courses_anonymous: Math.round(courses * 0.6),
      saved: Math.round(courses * 0.2),
    };
  });
  const dau = daily[daily.length - 1]?.dau ?? 0;
  const mau = 9_640;
  return {
    range: { from: daily[0]?.date ?? dayOffset(-29), to: dayOffset(0) },
    totals: {
      users: 21_480,
      dau,
      wau: 4_310,
      mau,
      new_users: daily.reduce((a, d) => a + d.new_users, 0),
      stickiness: Number((dau / mau).toFixed(3)),
      visitors: mau,
      logged_in: Math.round(mau * 0.3),
      anonymous: Math.round(mau * 0.7),
      page_views: daily.reduce((a, d) => a + d.page_views, 0),
      courses: daily.reduce((a, d) => a + d.courses, 0),
      courses_anonymous: daily.reduce((a, d) => a + d.courses_anonymous, 0),
    },
    daily,
    acquisition: [
      { channel: "인스타그램", users: 3120 },
      { channel: "검색", users: 2480 },
      { channel: "공유 링크", users: 1910 },
      { channel: "직접 방문", users: 1340 },
      { channel: "기타", users: 790 },
    ],
    providers: [
      { provider: "kakao", users: 12_860 },
      { provider: "naver", users: 5_410 },
      { provider: "google", users: 3_210 },
    ],
    devices: [
      { device: "mobile", users: 6_900 },
      { device: "desktop", users: 2_500 },
      { device: "tablet", users: 240 },
    ],
    cohorts: series(6, (date, i) => {
      const weeks = 6 - i;
      return {
        cohort: `${date.slice(5).replace("-", "/")} 주`,
        size: 900 + Math.round(hash(`c${i}`) * 500),
        retention: Array.from({ length: weeks }, (_, w) => (w === 0 ? 1 : Number((0.42 * Math.exp(-w * 0.28) + 0.08 + hash(`r${i}${w}`) * 0.04).toFixed(3)))),
      };
    }).map((c, i) => ({ ...c, cohort: `${dayOffset(-(6 - i) * 7).slice(5).replace("-", "/")} 주` })),
  };
}

export function recommendationAnalytics(): RecommendationAnalytics {
  const daily = series(30, (date, i) => {
    const weekend = [0, 5, 6].includes(new Date(date).getDay()) ? 1.5 : 1;
    const generated = Math.round((1400 + i * 22 + hash(`g${date}`) * 300) * weekend);
    return { date, generated, saved: Math.round(generated * (0.24 + hash(`s${date}`) * 0.06)), rerolled: Math.round(generated * (0.27 + hash(`x${date}`) * 0.08)) };
  });
  const generated = daily.reduce((a, d) => a + d.generated, 0);
  const saved = daily.reduce((a, d) => a + d.saved, 0);
  const rerolled = daily.reduce((a, d) => a + d.rerolled, 0);
  return {
    range: { from: daily[0]?.date ?? dayOffset(-29), to: dayOffset(0) },
    totals: {
      generated,
      save_rate: Number((saved / generated).toFixed(3)),
      reroll_rate: Number((rerolled / generated).toFixed(3)),
      swap_rate: 0.184,
      avg_budget: 46_300,
      avg_budget_utilization: 0.88,
      slot_empty_rate: 0.031,
      p95_latency_ms: 1_420,
    },
    daily,
    by_purpose: purposes.map((p, i) => ({
      purpose: p.code,
      purpose_name: p.name,
      generated: Math.round(generated * ([0.38, 0.14, 0.12, 0.22, 0.14][i] ?? 0.1)),
      save_rate: Number((0.2 + hash(`bp${p.code}`) * 0.14).toFixed(3)),
    })),
    budget_histogram: ["~2만", "2~4만", "4~6만", "6~8만", "8~10만", "10만~"].map((bucket, i) => ({
      bucket,
      count: Math.round(generated * ([0.12, 0.34, 0.26, 0.14, 0.08, 0.06][i] ?? 0.05)),
    })),
    heatmap: regions.flatMap((r) =>
      purposes.map((p) => ({
        region: r.slug,
        region_name: r.name,
        purpose: p.code,
        purpose_name: p.name,
        count: Math.round(hash(`${r.slug}:${p.code}`) ** 1.6 * 2400),
      })),
    ),
    latency: series(30, (date) => {
      const p50 = Math.round(520 + hash(`l${date}`) * 140);
      return { date, p50, p95: Math.round(p50 * (2.2 + hash(`m${date}`) * 0.7)) };
    }),
  };
}

export function topPlaces(): TopPlace[] {
  return places
    .filter((p) => p.status === "approved" || p.status === "pending")
    .slice(0, 10)
    .map((p) => {
      const impressions = Math.round(800 + hash(`i${p.id}`) * 5200);
      return {
        id: p.id,
        name: p.name,
        region_name: p.region?.name ?? "-",
        category_name: p.category_name,
        impressions,
        saves: Math.round(impressions * (0.08 + hash(`s${p.id}`) * 0.2)),
        swap_outs: Math.round(impressions * (0.03 + hash(`o${p.id}`) * 0.12)),
      };
    })
    .sort((a, b) => b.impressions - a.impressions);
}

export function systemHealth(): SystemHealth {
  const t = Date.now();
  return {
    status: "degraded",
    services: [
      { name: "PostgreSQL", status: "ok", latency_ms: 4 + (t % 5) },
      { name: "Redis", status: "ok", latency_ms: 1 + (t % 2) },
      { name: "Elasticsearch", status: "ok", latency_ms: 18 + (t % 9) },
      { name: "수집 워커", status: "ok", latency_ms: null },
      { name: "LLM 설명 생성", status: "degraded", latency_ms: 2300 + (t % 400) },
    ],
    checked_at: new Date().toISOString(),
  };
}
