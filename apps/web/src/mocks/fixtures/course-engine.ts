/**
 * ⚠️ 개발용 목 추천 엔진. 실제 알고리즘(docs/06)의 "모양"만 흉내 낸다:
 * 템플릿 → 슬롯별 예산 배분 → 예산 하드 필터 → 가장 잘 맞는 곳 선택 → 이동시간 계산.
 * 응답 스키마는 docs/03 과 같다. 화면 개발·데모 외의 용도로 쓰지 말 것.
 */
import type {
  Course,
  CourseDetail,
  CourseRole,
  GenerateCourseRequest,
  GenerateCourseResponse,
  NearbyEvent,
  PlaceSummary as ApiPlaceSummary,
  ScoreBreakdown,
  Stop,
  SwapStrategy,
  Transport,
} from "@/lib/api/types";
import { purposes, regions } from "./meta";

/** 목 장소는 가격을 항상 안다. (실제 API 는 무료이거나 가격을 모르면 price_per_person 이 null) */
type PlaceSummary = ApiPlaceSummary & { price_per_person: number };
/** 저장해 둔 코스의 장소를 다시 목 장소로 (목이 만든 것이라 가격은 늘 있다) */
const priced = (place: ApiPlaceSummary): PlaceSummary => ({ ...place, price_per_person: place.price_per_person ?? 0 });

interface Seed {
  name: string;
  category: string;
  category_name: string;
  price: number;
  tags: string[];
  rating: number;
  reviews: number;
}

const POOL: Record<string, Seed[]> = {
  MEAL: [
    { name: "즉석떡볶이 골목집", category: "food.snack", category_name: "분식", price: 8000, tags: ["가성비", "힙한"], rating: 4.3, reviews: 1240 },
    { name: "손칼국수 한그릇", category: "food.korean", category_name: "한식 · 칼국수", price: 9000, tags: ["가성비", "한식"], rating: 4.4, reviews: 932 },
    { name: "연남 덮밥집", category: "food.japanese", category_name: "일식 · 덮밥", price: 12000, tags: ["가성비", "조용한", "일식"], rating: 4.5, reviews: 812 },
    { name: "온기파스타", category: "food.western", category_name: "양식 · 파스타", price: 16000, tags: ["아늑한", "양식"], rating: 4.6, reviews: 655 },
    { name: "숯불 닭갈비 마당", category: "food.korean", category_name: "한식 · 닭갈비", price: 19000, tags: ["한식", "단체석"], rating: 4.4, reviews: 1508 },
    { name: "비스트로 연", category: "food.western", category_name: "양식 · 코스", price: 36000, tags: ["뷰맛집", "조용한", "양식"], rating: 4.7, reviews: 421 },
    { name: "한우 다이닝 결", category: "food.korean", category_name: "한식 · 코스", price: 45000, tags: ["조용한", "한식", "단체석"], rating: 4.8, reviews: 318 },
  ],
  CAFE: [
    { name: "골목커피", category: "cafe.coffee", category_name: "테이크아웃 커피", price: 3500, tags: ["가성비"], rating: 4.2, reviews: 540 },
    { name: "카페 책과밤", category: "cafe.dessert", category_name: "북카페 · 디저트", price: 6000, tags: ["조용한", "아늑한", "디저트"], rating: 4.6, reviews: 702 },
    { name: "카페 느린오후", category: "cafe.dessert", category_name: "디저트 카페", price: 7500, tags: ["사진 잘 나오는", "디저트"], rating: 4.5, reviews: 1120 },
    { name: "루프탑 무드", category: "cafe.coffee", category_name: "루프탑 · 시그니처 음료", price: 11000, tags: ["뷰맛집", "힙한"], rating: 4.4, reviews: 860 },
    { name: "디저트 아틀리에", category: "cafe.dessert", category_name: "디저트 플레이트", price: 13000, tags: ["사진 잘 나오는", "디저트"], rating: 4.7, reviews: 390 },
  ],
  ATTRACTION: [
    { name: "숲길 산책", category: "play.park", category_name: "무료 산책 코스", price: 0, tags: ["산책", "조용한"], rating: 4.6, reviews: 2210 },
    { name: "인생네컷 & 오락실", category: "play.game", category_name: "포토 · 게임", price: 7000, tags: ["실내", "힙한"], rating: 4.2, reviews: 480 },
    { name: "보드게임 라운지", category: "play.game", category_name: "실내 · 게임", price: 6000, tags: ["실내"], rating: 4.3, reviews: 367 },
    { name: "도자기 원데이 클래스", category: "play.class", category_name: "원데이 클래스", price: 32000, tags: ["체험", "실내"], rating: 4.8, reviews: 214 },
  ],
  CULTURE: [
    { name: "동네 미술관 기획전", category: "culture.exhibition", category_name: "전시", price: 5000, tags: ["전시", "실내", "조용한"], rating: 4.5, reviews: 330 },
    { name: "독립서점 & 갤러리", category: "culture.space", category_name: "문화공간", price: 0, tags: ["전시", "조용한"], rating: 4.6, reviews: 190 },
    { name: "미디어아트 뮤지엄", category: "culture.exhibition", category_name: "전시", price: 15000, tags: ["전시", "사진 잘 나오는", "실내"], rating: 4.4, reviews: 1420 },
  ],
  BAR: [
    { name: "을지 호프", category: "bar", category_name: "호프", price: 9000, tags: ["가성비", "시끄러운"], rating: 4.1, reviews: 990 },
    { name: "와인바 밤결", category: "bar", category_name: "와인바", price: 18000, tags: ["조용한", "아늑한"], rating: 4.6, reviews: 412 },
    { name: "하이볼 스탠드", category: "bar", category_name: "하이볼 바", price: 12000, tags: ["힙한"], rating: 4.4, reviews: 640 },
  ],
};

const STAY_MIN: Record<string, number> = { MEAL: 60, CAFE: 50, ATTRACTION: 50, CULTURE: 60, BAR: 70 };
const SPEED_KMH: Record<Transport, number> = { walk: 4.5, transit: 18, car: 22 };
const DETOUR: Record<Transport, number> = { walk: 1.3, transit: 1.3, car: 1.4 };
const D0: Record<Transport, number> = { walk: 900, transit: 2500, car: 6000 };

interface Slot {
  role: CourseRole;
  share: number;
  optional?: boolean;
}

function templateFor(purpose: string, perPerson: number): Slot[] {
  const base: Record<string, Slot[]> = {
    date: [{ role: "MEAL", share: 0.55 }, { role: "CAFE", share: 0.2 }, { role: "ATTRACTION", share: 0.05 }, { role: "BAR", share: 0.2, optional: true }],
    travel: [{ role: "ATTRACTION", share: 0.1 }, { role: "MEAL", share: 0.5 }, { role: "CULTURE", share: 0.2 }, { role: "CAFE", share: 0.2 }],
    family: [{ role: "MEAL", share: 0.65 }, { role: "CAFE", share: 0.2 }, { role: "ATTRACTION", share: 0.15 }],
    friends: [{ role: "MEAL", share: 0.5 }, { role: "ATTRACTION", share: 0.15 }, { role: "BAR", share: 0.35, optional: true }],
    solo: [{ role: "MEAL", share: 0.6 }, { role: "CAFE", share: 0.25 }, { role: "CULTURE", share: 0.15, optional: true }],
  };
  let slots = base[purpose] ?? base.date!;
  if (perPerson < 22000) slots = slots.filter((s) => !s.optional); // 예산이 빠듯하면 optional 슬롯 제거 (docs/06 §1-3)
  const sum = slots.reduce((acc, s) => acc + s.share, 0);
  return slots.map((s) => ({ ...s, share: s.share / sum }));
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

function haversine(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function placesFor(regionSlug: string, role: CourseRole): PlaceSummary[] {
  const region = regions.find((r) => r.slug === regionSlug) ?? regions[0]!;
  return (POOL[role] ?? []).map((seed, i) => {
    const id = `p_${region.slug}_${String(role).toLowerCase()}_${i}`;
    const angle = hash(id) * Math.PI * 2;
    const radius = (0.15 + hash(`${id}r`) * 0.6) * region.radius_m;
    const lat = region.center.lat + (Math.sin(angle) * radius) / 111_320;
    const lng = region.center.lng + (Math.cos(angle) * radius) / (111_320 * Math.cos((region.center.lat * Math.PI) / 180));
    return {
      id,
      name: seed.name,
      category: seed.category,
      category_name: seed.category_name,
      lat: Number(lat.toFixed(6)),
      lng: Number(lng.toFixed(6)),
      address: `${region.parent?.name ?? ""} ${region.name} ${Math.round(hash(`${id}a`) * 80) + 1}길 ${Math.round(hash(`${id}b`) * 40) + 1}`.trim(),
      thumbnail_url: null,
      rating: seed.rating,
      review_count: seed.reviews,
      price_per_person: seed.price,
      is_free: seed.price === 0,
      tags: seed.tags,
    };
  });
}

function budgetFit(price: number, slotBudget: number, share: number): number {
  if (price === 0) return share <= 0.1 ? 0.9 : 0.6;
  const u = price / slotBudget;
  const at = (x: number) => Math.exp(-((x - 0.85) ** 2) / (2 * (x < 0.85 ? 0.18 * 1.6 : 0.18) ** 2));
  if (u <= 1) return at(u);
  return Math.max(0, at(1) - 4 * (u - 1));
}

type Variant = "best" | "value" | "near";

function pick(cands: PlaceSummary[], slotBudget: number, share: number, prev: { lat: number; lng: number }, variant: Variant, liked: string[], mode: Transport, cap: number) {
  const pool = cands.filter((p) => p.price_per_person <= Math.min(slotBudget * 1.25, cap));
  if (pool.length === 0) return null;
  const scored = pool.map((p) => {
    const d = haversine(prev, p);
    const budget = budgetFit(p.price_per_person, variant === "value" ? slotBudget * 0.7 : slotBudget, share);
    const dist = Math.exp(-d / D0[mode]);
    const pref = liked.length ? Math.min(1, 0.4 + 0.3 * p.tags.filter((t) => liked.includes(t)).length) : 0.5;
    const rating = Math.min(1, Math.max(0, ((p.rating ?? 4) - 3) / 2));
    const s = variant === "near" ? budget * 0.2 + dist * 0.6 + rating * 0.2 : budget * 0.45 + dist * 0.15 + rating * 0.2 + pref * 0.2;
    return { p, s };
  });
  scored.sort((a, b) => b.s - a.s);
  return scored[0]!.p;
}

function breakdown(p: PlaceSummary, slotBudget: number, share: number, dist: number, liked: string[], mode: Transport): ScoreBreakdown {
  const r = (k: string, lo: number, hi: number) => Number((lo + hash(p.id + k) * (hi - lo)).toFixed(2));
  return {
    budget: Number(budgetFit(p.price_per_person, slotBudget, share).toFixed(2)),
    distance: Number(Math.exp(-dist / D0[mode]).toFixed(2)),
    rating: Number(Math.min(1, Math.max(0, ((p.rating ?? 4) - 3) / 2)).toFixed(2)),
    sentiment: r("s", 0.6, 0.92),
    congestion: r("c", 0.35, 0.85),
    time_fit: r("t", 0.7, 0.95),
    preference: liked.length ? Number(Math.min(1, 0.4 + 0.3 * p.tags.filter((t) => liked.includes(t)).length).toFixed(2)) : 0.5,
    purpose_fit: r("p", 0.55, 0.9),
    curated: 0,
    buzz: r("z", 0.2, 0.95),
  };
}

const WEIGHTS: ScoreBreakdown = { budget: 0.24, distance: 0.12, rating: 0.16, sentiment: 0.14, congestion: 0.08, time_fit: 0.08, preference: 0.12, purpose_fit: 0.06, curated: 0, buzz: 0 };

function reasonFor(b: ScoreBreakdown, p: PlaceSummary): string {
  const top = (Object.keys(b) as (keyof ScoreBreakdown)[]).sort((x, y) => b[y] * WEIGHTS[y] - b[x] * WEIGHTS[x]).slice(0, 2);
  // [이어지는 말, 끝맺는 말]
  const say: Record<keyof ScoreBreakdown, [string, string]> = {
    budget: p.is_free ? ["돈이 들지 않아 예산을 아껴 주고,", "돈이 들지 않아 예산을 아껴 줘요"] : ["배정된 예산에 딱 맞고,", "배정된 예산에 딱 맞아요"],
    distance: ["앞 장소에서 가깝고,", "앞 장소에서 가까워요"],
    rating: [`리뷰 ${p.review_count.toLocaleString("ko-KR")}개로 검증됐고,`, `리뷰 ${p.review_count.toLocaleString("ko-KR")}개에 평점 ${p.rating}점이에요`],
    sentiment: ["최근 리뷰 분위기가 좋고,", "최근 리뷰 분위기가 좋아요"],
    congestion: ["도착할 시간에 한산한 편이고,", "도착할 시간에 한산한 편이에요"],
    time_fit: ["이 시간대에 가기 좋고,", "이 시간대에 가기 좋아요"],
    preference: ["고르신 취향과 잘 맞고,", "고르신 취향과 잘 맞아요"],
    purpose_fit: ["오늘 모임에 잘 어울리고,", "오늘 모임에 잘 어울려요"],
    curated: ["한국관광공사가 소개한 곳이고,", "한국관광공사가 소개한 곳이에요"],
    buzz: ["가게가 모여 있는 거리에 있고,", "가게가 모여 있는 북적이는 거리에 있어요"],
  };
  const [a, c] = top;
  if (!a) return "예산 안에서 가장 잘 맞는 곳이에요";
  return c ? `${say[a][0]} ${say[c][1]}` : say[a][1];
}

interface BuildContext {
  req: GenerateCourseRequest;
  regionSlug: string;
}

function buildStops(ctx: BuildContext, chosen: { slot: Slot; place: PlaceSummary }[]): Stop[] {
  const { req } = ctx;
  const mode = req.transport ?? "walk";
  const n = req.party_size;
  const perPerson = req.budget_total / n;
  const region = regions.find((r) => r.slug === ctx.regionSlug) ?? regions[0]!;
  const liked = req.preferences?.liked_tags ?? [];
  let cursor = new Date(req.start_at ?? Date.now()).getTime();
  let prev: { lat: number; lng: number } = req.origin ?? region.center;

  return chosen.map(({ slot, place }, i) => {
    const straight = haversine(prev, place);
    const distance_m = Math.round(straight * DETOUR[mode]);
    const travel_min = Math.max(1, Math.round((distance_m / 1000 / SPEED_KMH[mode]) * 60));
    cursor += travel_min * 60_000;
    const arrive = cursor;
    cursor += (STAY_MIN[slot.role] ?? 50) * 60_000;
    const b = breakdown(place, perPerson * slot.share, slot.share, straight, liked, mode);
    const score = (Object.keys(b) as (keyof ScoreBreakdown)[]).reduce((acc, k) => acc + b[k] * WEIGHTS[k], 0);
    const congestionValue = Number((1 - b.congestion).toFixed(2));
    prev = place;
    return {
      position: i + 1,
      role: slot.role,
      place,
      arrive_at: iso(arrive),
      leave_at: iso(cursor),
      est_price: place.price_per_person * n,
      from_prev: { travel_min, distance_m, mode },
      score: Number(score.toFixed(2)),
      score_breakdown: b,
      reason: reasonFor(b, place),
      congestion: { level: congestionValue < 0.35 ? "여유" : congestionValue < 0.6 ? "보통" : "붐빔", value: congestionValue },
    };
  });
}

function iso(ms: number): string {
  const kst = new Date(ms + 9 * 3_600_000);
  return `${kst.toISOString().slice(0, 19)}+09:00`;
}

function finalize(id: string, label: string, ctx: BuildContext, stops: Stop[], warnings: Course["warnings"]): Course {
  const n = ctx.req.party_size;
  const price = stops.reduce((acc, s) => acc + s.est_price, 0);
  const travel_min = stops.reduce((acc, s) => acc + (s.from_prev?.travel_min ?? 0), 0);
  const distance_m = stops.reduce((acc, s) => acc + (s.from_prev?.distance_m ?? 0), 0);
  const first = stops[0];
  const last = stops[stops.length - 1];
  const duration_min = first && last ? Math.round((new Date(last.leave_at).getTime() - new Date(first.arrive_at).getTime()) / 60_000) : 0;
  const who = n === 1 ? "혼자서" : n === 2 ? "둘이서" : `${n}명이서`;
  const modeWord = ctx.req.transport === "car" ? "차로" : ctx.req.transport === "transit" ? "대중교통으로" : "걸어서";
  return {
    id,
    label,
    summary: `${who} ${price.toLocaleString("ko-KR")}원, ${modeWord} ${travel_min}분이면 충분해요`,
    totals: {
      price,
      price_per_person: Math.round(price / n),
      budget_left: ctx.req.budget_total - price,
      budget_utilization: Number((price / ctx.req.budget_total).toFixed(2)),
      travel_min,
      distance_m,
      duration_min,
      score: Number((stops.reduce((acc, s) => acc + s.score, 0) / Math.max(1, stops.length)).toFixed(2)),
    },
    stops,
    route: { polyline: null, optimizer: "held_karp" },
    warnings,
  };
}

// ── 저장소 (브라우저: sessionStorage 백업 → 새로고침해도 유지) ─────────────
interface StoredCourse {
  course: Course;
  req: GenerateCourseRequest;
  regionSlug: string;
  siblings: { id: string; label: string }[];
  events: NearbyEvent[];
  saved?: boolean;
}
const memory = new Map<string, StoredCourse>();
const STORAGE_KEY = "njd_mock_courses";

function persist() {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...memory.entries()].slice(-30)));
  } catch {
    // 용량 초과 등은 무시
  }
}
function hydrate() {
  if (memory.size > 0 || typeof sessionStorage === "undefined") return;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) for (const [k, v] of JSON.parse(raw) as [string, StoredCourse][]) memory.set(k, v);
  } catch {
    // 손상된 값은 버린다
  }
}

export class MockProblem extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    title: string,
    readonly detail?: string,
    readonly meta?: Record<string, unknown>,
  ) {
    super(title);
  }
}

export function eventsNear(regionSlug: string): NearbyEvent[] {
  const region = regions.find((r) => r.slug === regionSlug) ?? regions[0]!;
  const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
  return [
    { id: `e_${region.slug}_1`, title: `${region.name} 가을 거리축제`, ends_on: day(8), distance_m: 640, is_free: true },
    { id: `e_${region.slug}_2`, title: "플리마켓 & 버스킹 위크", ends_on: day(3), distance_m: 910, is_free: true },
    { id: `e_${region.slug}_3`, title: "미디어아트 특별전", ends_on: day(21), distance_m: 1240, is_free: false },
  ];
}

export function generate(req: GenerateCourseRequest): GenerateCourseResponse {
  hydrate();
  const started = Date.now();
  const regionSlug = req.region ?? regions[0]!.slug;
  const region = regions.find((r) => r.slug === regionSlug);
  if (!region) throw new MockProblem(404, "REGION_NOT_FOUND", "지역을 찾을 수 없어요", `'${regionSlug}' 지역은 등록돼 있지 않아요.`);
  if (!purposes.some((p) => p.code === req.purpose)) throw new MockProblem(422, "VALIDATION_ERROR", "목적을 확인해 주세요", "알 수 없는 목적 코드예요.");

  const n = Math.max(1, req.party_size);
  const perPerson = req.budget_total / n;
  const slots = templateFor(req.purpose, perPerson);
  const minPerPerson = slots.reduce((acc, s) => acc + Math.min(...(POOL[s.role] ?? [{ price: 0 }]).map((p) => p.price)), 0);
  if (perPerson < minPerPerson) {
    const min = Math.ceil((minPerPerson * n) / 1000) * 1000;
    throw new MockProblem(422, "BUDGET_TOO_LOW", "예산이 너무 낮아요", `${region.name}에서 ${n}명 기준 최소 ${min.toLocaleString("ko-KR")}원이 필요해요.`, { min_budget: min });
  }

  const ctx: BuildContext = { req: { ...req, party_size: n }, regionSlug };
  const mode = req.transport ?? "walk";
  const liked = req.preferences?.liked_tags ?? [];
  const exclude = new Set(req.preferences?.exclude_place_ids ?? []);
  const requestId = `req_${started.toString(36)}`;
  const variants: [Variant, string][] = [["best", "추천 코스"], ["value", "가성비 코스"], ["near", "덜 걷는 코스"]];
  const count = Math.min(variants.length, 1 + (req.alternatives ?? 2));

  const built = variants.slice(0, count).map(([variant, label], vi) => {
    const warnings: Course["warnings"] = [];
    const chosen: { slot: Slot; place: PlaceSummary }[] = [];
    let prev: { lat: number; lng: number } = req.origin ?? region.center;
    let spent = 0;
    let carry = 0; // 앞 슬롯에서 아낀 돈은 뒤 슬롯으로 이월 (docs/06 §5)
    for (const slot of slots) {
      const slotBudget = perPerson * slot.share + carry;
      const cands = placesFor(regionSlug, slot.role).filter((p) => !exclude.has(p.id) && !chosen.some((c) => c.place.id === p.id));
      const place = pick(cands, slotBudget, slot.share, prev, variant, liked, mode, perPerson - spent);
      if (!place) {
        warnings.push({ code: "SLOT_EMPTY", role: slot.role, message: "이 예산으로 갈 수 있는 곳을 찾지 못해 한 곳을 비워 뒀어요." });
        continue;
      }
      carry = Math.max(0, slotBudget - place.price_per_person);
      spent += place.price_per_person;
      chosen.push({ slot, place });
      prev = place;
    }
    const id = `c_${started.toString(36)}${vi}`;
    return finalize(id, label, ctx, buildStops(ctx, chosen), warnings);
  });

  const siblings = built.map((c) => ({ id: c.id, label: c.label }));
  const events = eventsNear(regionSlug);
  for (const course of built) memory.set(course.id, { course, req: ctx.req, regionSlug, siblings, events });
  persist();

  return {
    request_id: requestId,
    courses: built,
    nearby_events: events,
    meta: { engine_version: "mock-1.0.0", scoring_profile: `${req.purpose}@mock`, candidates: 180 + Math.round(hash(requestId) * 80), latency_ms: Date.now() - started + 600 },
  };
}

function ensureDemo(id: string) {
  if (!id.startsWith("demo") || memory.has(id)) return;
  const start = new Date();
  start.setHours(18, 0, 0, 0);
  const res = generate({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 40000, transport: "walk", start_at: iso(start.getTime()), alternatives: 2 });
  const first = memory.get(res.courses[0]!.id);
  if (first) memory.set(id, { ...first, course: { ...first.course, id } });
}

export function getStored(id: string): StoredCourse {
  hydrate();
  ensureDemo(id);
  const found = memory.get(id);
  if (!found) throw new MockProblem(404, "COURSE_NOT_FOUND", "코스를 찾을 수 없어요", "저장하지 않은 코스는 24시간 뒤에 지워져요.");
  return found;
}

export function getDetail(id: string): CourseDetail {
  const s = getStored(id);
  const region = regions.find((r) => r.slug === s.regionSlug) ?? null;
  const purpose = purposes.find((p) => p.code === s.req.purpose);
  return {
    ...s.course,
    request: {
      region: region ? { slug: region.slug, name: region.name } : null,
      purpose: { code: s.req.purpose, name: purpose?.name ?? s.req.purpose },
      party_size: s.req.party_size,
      budget_total: s.req.budget_total,
      transport: s.req.transport ?? "walk",
      start_at: s.req.start_at ?? s.course.stops[0]?.arrive_at ?? new Date().toISOString(),
    },
    siblings: s.siblings,
    nearby_events: s.events,
    og: {
      title: `${region?.name ?? "우리 동네"} ${purpose?.name ?? ""} 코스 · ${s.course.totals.price.toLocaleString("ko-KR")}원`,
      description: s.course.summary,
      image_url: null,
    },
    is_saved: s.saved ?? false,
  };
}

export function swap(id: string, position: number, strategy: SwapStrategy): Course {
  const s = getStored(id);
  const index = s.course.stops.findIndex((st) => st.position === position);
  const target = s.course.stops[index];
  if (!target) throw new MockProblem(422, "VALIDATION_ERROR", "바꿀 장소를 찾지 못했어요");
  const used = new Set(s.course.stops.map((st) => st.place.id));
  const targetPrice = target.place.price_per_person ?? 0;
  const room = s.course.totals.budget_left / s.req.party_size + targetPrice;
  const prevPoint = s.course.stops[index - 1]?.place ?? regions.find((r) => r.slug === s.regionSlug)?.center ?? target.place;
  let cands = placesFor(s.regionSlug, target.role).filter((p) => !used.has(p.id) && p.price_per_person <= room);
  if (strategy === "cheaper") cands = cands.filter((p) => p.price_per_person < targetPrice).sort((a, b) => b.price_per_person - a.price_per_person);
  else if (strategy === "closer") cands = cands.sort((a, b) => haversine(prevPoint, a) - haversine(prevPoint, b));
  else if (strategy === "higher_rated") cands = cands.filter((p) => (p.rating ?? 0) >= (target.place.rating ?? 0)).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  else cands = cands.sort((a, b) => hash(a.id + Date.now()) - hash(b.id + Date.now()));
  const next = cands[0];
  // 실제 API 가 내는 코드와 맞춘다 (SLOT_EMPTY 는 코스의 경고 코드지 교체 실패 코드가 아니다)
  if (!next) throw new MockProblem(422, "SWAP_NOT_POSSIBLE", "바꿀 만한 곳이 없어요", "이 조건으로는 예산 안에서 대신할 곳을 찾지 못했어요.");

  const slots = templateFor(s.req.purpose, s.req.budget_total / s.req.party_size);
  const chosen = s.course.stops.map((st, i) => ({
    slot: slots.find((sl) => sl.role === st.role) ?? { role: st.role, share: 0.2 },
    place: i === index ? next : priced(st.place),
  }));
  const course = finalize(id, s.course.label, { req: s.req, regionSlug: s.regionSlug }, buildStops({ req: s.req, regionSlug: s.regionSlug }, chosen), s.course.warnings);
  memory.set(id, { ...s, course });
  persist();
  return course;
}

export function reorder(id: string, order: number[]): Course {
  const s = getStored(id);
  const slots = templateFor(s.req.purpose, s.req.budget_total / s.req.party_size);
  const chosen = order
    .map((pos) => s.course.stops.find((st) => st.position === pos))
    .filter((st): st is Stop => Boolean(st))
    .map((st) => ({ slot: slots.find((sl) => sl.role === st.role) ?? { role: st.role, share: 0.2 }, place: priced(st.place) }));
  if (chosen.length !== s.course.stops.length) throw new MockProblem(422, "VALIDATION_ERROR", "순서를 확인해 주세요");
  const ctx = { req: s.req, regionSlug: s.regionSlug };
  const course = { ...finalize(id, s.course.label, ctx, buildStops(ctx, chosen), s.course.warnings), route: { polyline: null, optimizer: "user_order" } };
  memory.set(id, { ...s, course });
  persist();
  return course;
}

export function markSaved(id: string, saved: boolean) {
  const s = getStored(id);
  memory.set(id, { ...s, saved });
  persist();
}

export function listSaved(): StoredCourse[] {
  hydrate();
  return [...memory.values()].filter((s) => s.saved);
}
