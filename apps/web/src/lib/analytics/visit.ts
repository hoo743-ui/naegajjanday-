/**
 * 1자 방문 기록 (docs/50): 페이지를 볼 때마다 API 에 한 줄. 로그인 여부는 서버가 토큰으로 안다.
 * 이 브라우저의 임의 id 만 보낸다 — 서버는 그것도 해시로만 저장하고, IP 는 남기지 않는다.
 * 실패해도 화면에는 아무 일도 없다.
 */
import { api } from "@/lib/api/client";

const KEY = "njd.visitor";
let memoryId: string | null = null;

/** 이 브라우저의 임의 id. 방문 기록과 1자 이벤트(docs/62)가 같은 번호를 쓴다 — 서버는 둘 다 같은 해시로 저장 */
export function visitorId(): string {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved) return saved;
    const fresh = crypto.randomUUID();
    window.localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    // 시크릿 창 · 저장소 차단: 이 탭 동안만 같은 사람
    memoryId ??= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    return memoryId;
  }
}

let lastPath = "";

export function recordVisit(path: string): void {
  if (typeof window === "undefined" || path.startsWith("/admin") || path === lastPath) return;
  lastPath = path;
  const referrer = document.referrer || undefined;
  void api.post("/visits", { visitor_id: visitorId(), path: path.slice(0, 200), ...(referrer ? { referrer } : {}) }).catch(() => undefined);
}
