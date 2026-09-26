/**
 * 1자 이벤트 수집 (docs/62): track() 이 부른 이벤트를 우리 API(`POST /v1/events`)로도 보낸다.
 * 외부 분석 키가 없어도 "만든 코스가 쓰였는가"를 셀 수 있게. 화면을 절대 막지 않는다 —
 *  - 모아서 보낸다(최대 20개 또는 4초), 페이지를 떠날 때(pagehide · 숨김)는 navigator.sendBeacon
 *  - 실패하면 버린다(재시도 없음). 응답을 기다리는 화면은 없다
 *  - Do-Not-Track · Global Privacy Control 이 켜져 있거나 `njd.analytics_optout = "1"` 이면 보내지 않는다
 *  - 보내는 것: 카탈로그의 이벤트 이름, 짧은 값의 속성(서버가 이벤트별 허용 목록으로 한 번 더 거른다),
 *    코스 id, 시각, 경로(쿼리 없이), 이 브라우저의 임의 번호(njd.visitor — 서버는 해시로만 저장).
 *    한 줄 말 같은 자유 글은 카탈로그에 없다. 로그인했다면 토큰을 실어 서버가 계정을 안다(beacon 은 못 싣는다)
 */
import { getAccessToken } from "@/lib/auth/token";
import { API_URL, IS_MOCKING } from "@/lib/api/client";
import { visitorId } from "./visit";

const OPT_OUT_KEY = "njd.analytics_optout";
const MAX_BATCH = 20;
const FLUSH_MS = 4_000;
const MAX_QUEUE = 200;
const MAX_STR = 64;

interface Pending {
  name: string;
  props: Record<string, string | number | boolean>;
  course_id?: string;
  ts: number;
  path: string;
}

let queue: Pending[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let listening = false;
let allowed: boolean | null = null;

function isAllowed(): boolean {
  if (allowed !== null) return allowed;
  if (typeof window === "undefined" || IS_MOCKING) return (allowed = false);
  const nav = navigator as Navigator & { globalPrivacyControl?: boolean; msDoNotTrack?: string };
  const win = window as Window & { doNotTrack?: string };
  const dnt = nav.doNotTrack ?? win.doNotTrack ?? nav.msDoNotTrack;
  if (dnt === "1" || dnt === "yes" || nav.globalPrivacyControl === true) return (allowed = false);
  try {
    if (window.localStorage.getItem(OPT_OUT_KEY) === "1") return (allowed = false);
  } catch {
    // 저장소를 못 써도 수집 자체는 된다 (번호는 이 탭 동안만 같다)
  }
  return (allowed = true);
}

/** 이 브라우저에서 1자 이벤트를 끄거나 켠다 (개인정보처리방침에 적힌 방법) */
export function setFirstPartyOptOut(off: boolean): void {
  try {
    if (off) window.localStorage.setItem(OPT_OUT_KEY, "1");
    else window.localStorage.removeItem(OPT_OUT_KEY);
  } catch {
    // 저장소를 못 쓰면 이번 탭에만 적용
  }
  allowed = off ? false : null;
  if (off) queue = [];
}

function scalarProps(props: Record<string, unknown>): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(props)) {
    if (key === "course_id") continue;
    if (typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) out[key] = value;
    else if (typeof value === "string" && value.length <= MAX_STR) out[key] = value;
  }
  return out;
}

function body(events: Pending[]): string {
  return JSON.stringify({ device_id: visitorId(), events });
}

function send(events: Pending[], leaving: boolean): void {
  if (events.length === 0) return;
  const url = `${API_URL}/events`;
  const payload = body(events);
  if (leaving && typeof navigator.sendBeacon === "function") {
    // text/plain: CORS 사전 요청 없이 나간다. 서버는 본문을 JSON 으로 읽는다
    try {
      if (navigator.sendBeacon(url, new Blob([payload], { type: "text/plain;charset=UTF-8" }))) return;
    } catch {
      // beacon 이 거절되면 아래 keepalive fetch 로
    }
  }
  const token = getAccessToken();
  try {
    void fetch(url, {
      method: "POST",
      keepalive: true,
      credentials: "omit",
      headers: { "Content-Type": "text/plain;charset=UTF-8", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: payload,
    }).catch(() => undefined);
  } catch {
    // 분석 실패가 화면을 깨면 안 된다
  }
}

export function flushFirstParty(leaving = false): void {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  while (queue.length > 0) send(queue.splice(0, MAX_BATCH), leaving);
}

function listen(): void {
  if (listening) return;
  listening = true;
  const leave = () => flushFirstParty(true);
  window.addEventListener("pagehide", leave);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") leave();
  });
}

export function recordFirstParty(name: string, props: Record<string, unknown>): void {
  if (!isAllowed()) return;
  const path = window.location.pathname;
  if (path.startsWith("/admin")) return;
  listen();
  const courseId = typeof props.course_id === "string" ? props.course_id : undefined;
  if (queue.length >= MAX_QUEUE) queue.shift();
  queue.push({ name, props: scalarProps(props), ...(courseId ? { course_id: courseId } : {}), ts: Date.now(), path: path.slice(0, 200) });
  if (queue.length >= MAX_BATCH) flushFirstParty();
  else timer ??= setTimeout(() => flushFirstParty(), FLUSH_MS);
}
