import type { CourseRole, ScoreFeature, Transport } from "@/lib/api/types";

const KRW = new Intl.NumberFormat("ko-KR");

/** 36000 → "36,000원" */
export function won(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${KRW.format(Math.round(value))}원`;
}

/** 36000 → "3.6만원", 8000 → "8천원" — 좁은 칩·축 라벨용 */
export function wonCompact(value: number): string {
  if (value === 0) return "0원";
  if (value >= 10_000) {
    const man = value / 10_000;
    return `${Number.isInteger(man) ? man : man.toFixed(1)}만원`;
  }
  if (value >= 1_000 && value % 1_000 === 0) return `${value / 1_000}천원`;
  return won(value);
}

export function num(value: number): string {
  return KRW.format(value);
}

/** 225 → "3시간 45분" */
export function minutes(value: number): string {
  const total = Math.max(0, Math.round(value));
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}분`;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

/** 1320 → "1.3km", 350 → "350m" */
export function distance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}km`;
  return `${Math.round(meters / 10) * 10}m`;
}

export function percent(ratio: number, digits = 0): string {
  return `${(ratio * 100).toFixed(digits)}%`;
}

const TIME = new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Seoul" });
const DATE = new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric", weekday: "short", timeZone: "Asia/Seoul" });
const DATE_SHORT = new Intl.DateTimeFormat("ko-KR", { month: "numeric", day: "numeric", timeZone: "Asia/Seoul" });

export function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--" : TIME.format(d);
}

export function dateLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : DATE.format(d);
}

export function dateShort(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : DATE_SHORT.format(d);
}

export function dateRange(from: string, to: string): string {
  return `${dateShort(from)} ~ ${dateShort(to)}`;
}

/** 오늘부터 며칠 남았는지. 지난 날짜면 음수. */
export function daysUntil(iso: string): number {
  const end = new Date(iso);
  const now = new Date();
  return Math.ceil((end.getTime() - now.getTime()) / 86_400_000);
}

/** 로컬 시각을 +09:00 오프셋 ISO 로 (API 규약) */
export function toKstIso(date: Date): string {
  const kst = new Date(date.getTime() + 9 * 3_600_000);
  return `${kst.toISOString().slice(0, 19)}+09:00`;
}

// ── 도메인 어휘(표시용 라벨). 데이터가 아니라 API enum 의 번역이다. ──
const ROLE_LABEL: Record<string, string> = {
  MEAL: "식사",
  CAFE: "카페",
  DESSERT: "디저트",
  ATTRACTION: "볼거리",
  CULTURE: "문화",
  ACTIVITY: "놀거리",
  BAR: "한잔",
  NIGHTVIEW: "야경",
};
export function roleLabel(role: CourseRole): string {
  return ROLE_LABEL[role] ?? role;
}

const TRANSPORT_LABEL: Record<Transport, string> = { walk: "도보", transit: "대중교통", car: "자동차" };
export function transportLabel(mode: Transport): string {
  return TRANSPORT_LABEL[mode] ?? mode;
}

/** docs/06 §3 의 8개 피처 + 코스 스타일용 buzz. 사용자가 읽는 말로 풀어쓴다. */
export const FEATURE_INFO: Record<ScoreFeature, { label: string; hint: string }> = {
  budget: { label: "예산 적합도", hint: "배정된 예산의 85% 안팎을 쓰는 곳이 가장 높아요. 너무 싸도, 넘어도 감점." },
  distance: { label: "거리", hint: "이전 장소에서 가까울수록 높아요." },
  rating: { label: "평점", hint: "리뷰 수로 보정한 평점이에요. 리뷰 3개짜리 5.0은 높게 치지 않아요." },
  sentiment: { label: "리뷰 분위기", hint: "최근 리뷰의 긍정·부정을 분석했어요." },
  congestion: { label: "한산함", hint: "도착 예상 시각에 덜 붐빌수록 높아요." },
  time_fit: { label: "시간대", hint: "영업 마감까지 여유가 있고, 그 시간에 어울리는 곳인지 봐요." },
  preference: { label: "내 취향", hint: "고른 태그와 저장·피드백 이력이 반영돼요." },
  purpose_fit: { label: "목적 적합", hint: "오늘 모임의 목적과 잘 맞는 분위기인지 봐요." },
  curated: { label: "공공기관 소개", hint: "한국관광공사 관광정보에 실린 곳이에요. 평점 대신 쓰는 선별 기준이에요." },
  buzz: { label: "북적이는 거리", hint: "걸어서 2분 안에 가게가 얼마나 모여 있는지예요. '재미 우선' 코스에서만 점수에 들어가요." },
};
