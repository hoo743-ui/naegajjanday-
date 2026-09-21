/** "언제 만나요?" 의 순수 로직 — 날짜·시각·소요 시간을 API 의 start_at / duration_min 으로 바꾼다. */

export interface MeetTimeValues {
  /** "" = 오늘, 아니면 "YYYY-MM-DD" */
  meet_day: string;
  /** "" = 지금 바로(오늘만), 아니면 "HH:mm" */
  start_time: string;
  /** null = 짠이에게 맡기기 */
  duration_min: number | null;
}

export const START_PRESETS = [
  { label: "점심", time: "12:00" },
  { label: "오후", time: "14:00" },
  { label: "저녁", time: "18:00" },
  { label: "밤", time: "20:00" },
] as const;

export const DURATION_PRESETS = [
  { label: "2시간", minutes: 120, hint: "두 곳" },
  { label: "3시간", minutes: 180, hint: "세 곳" },
  { label: "4시간", minutes: 240, hint: "네 곳" },
  { label: "반나절", minutes: 360, hint: "6시간" },
  { label: "하루 종일", minutes: 480, hint: "8시간" },
] as const;

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"] as const;
const pad = (n: number) => String(n).padStart(2, "0");

export function toDayString(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

/** 오늘 · 내일 · 다가오는 토/일. 오늘이나 내일과 겹치는 주말 칩은 만들지 않는다. */
export function dayOptions(now: Date): { label: string; value: string }[] {
  const today = toDayString(now);
  const options = [
    { label: "오늘", value: "" },
    { label: "내일", value: toDayString(addDays(now, 1)) },
  ];
  for (const target of [6, 0]) {
    const ahead = (target - now.getDay() + 7) % 7;
    const value = toDayString(addDays(now, ahead));
    if (value === today || options.some((o) => o.value === value)) continue;
    options.push({ label: `이번 ${WEEKDAY[target]}요일`, value });
  }
  return options;
}

export function isToday(values: Pick<MeetTimeValues, "meet_day">, now: Date): boolean {
  return values.meet_day === "" || values.meet_day === toDayString(now);
}

/** 만나는 시각. "지금 바로"는 now 그대로. */
export function resolveStart(values: Pick<MeetTimeValues, "meet_day" | "start_time">, now: Date): Date {
  const base = values.meet_day ? new Date(`${values.meet_day}T00:00:00`) : new Date(now);
  if (!values.start_time) {
    // 다른 날인데 시각이 없으면 저녁 약속으로 본다 (UI 는 이 조합을 만들지 않는다 — 방어용)
    if (!isToday(values, now)) base.setHours(18, 0, 0, 0);
    return base;
  }
  const [h, m] = values.start_time.split(":").map(Number);
  base.setHours(h ?? 0, m ?? 0, 0, 0);
  return base;
}

/** 이미 지난 시각인가 (5분 여유). 지난 시각으로 코스를 짜면 영업시간·혼잡도 계산이 전부 틀어진다. */
export function isPast(values: Pick<MeetTimeValues, "meet_day" | "start_time">, now: Date): boolean {
  if (!values.start_time && isToday(values, now)) return false;
  return resolveStart(values, now).getTime() < now.getTime() - 5 * 60_000;
}

/** "9월 26일 (토) 18:00 ~ 21:00" */
export function describeWindow(values: MeetTimeValues, now: Date): string {
  const start = resolveStart(values, now);
  const day = isToday(values, now) ? "오늘" : `${start.getMonth() + 1}월 ${start.getDate()}일 (${WEEKDAY[start.getDay()]})`;
  const hm = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const from = !values.start_time && isToday(values, now) ? "지금" : hm(start);
  if (values.duration_min === null) return `${day} ${from}부터 · 끝나는 시간은 짠이가 맞춰요`;
  const end = new Date(start.getTime() + values.duration_min * 60_000);
  return `${day} ${from} ~ ${hm(end)}`;
}
