/**
 * 토큰 보관 규칙
 *  - access token: 메모리에만 둔다 (localStorage 금지 → XSS로 탈취돼도 15분짜리, 새로고침하면 사라짐)
 *  - refresh token: 서버가 심는 HttpOnly 쿠키 `rt`. JS에서는 볼 수 없고 `/auth/refresh` 호출에만 실린다.
 *  - 새로고침 직후에는 AuthProvider 가 refreshAccessToken() 을 한 번 불러 세션을 복원한다.
 */
import { parseErrorResponse, type ApiError } from "@/lib/api/client";
import { mockReady } from "@/lib/api/mock-ready";
import type { TokenResponse } from "@/lib/api/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1").replace(/\/$/, "");

let accessToken: string | null = null;
let expiresAt = 0;
let inflight: Promise<string | null> | null = null;
const listeners = new Set<(token: string | null) => void>();

/**
 * 로그인한 적이 있다는 흔적 (docs/28). 흔적이 없는 방문자에게는 새로고침 때 refresh 를 부르지 않는다 —
 * 부르면 401 이 돌아오고, 브라우저가 그것을 모든 페이지의 콘솔 오류로 남겼다(점검에서 59건).
 * 흔적은 로그인 버튼을 누를 때 · refresh 가 성공할 때 남기고, refresh 가 거절되거나 로그아웃하면 지운다.
 */
const SESSION_HINT = "njd_session";

export function hasSessionHint(): boolean {
  try {
    return localStorage.getItem(SESSION_HINT) === "1";
  } catch {
    return true; // 저장소를 못 쓰면 알 수 없다 → 예전처럼 한 번 시도한다
  }
}

export function markSession(on: boolean): void {
  try {
    if (on) localStorage.setItem(SESSION_HINT, "1");
    else localStorage.removeItem(SESSION_HINT);
  } catch {
    // 저장소를 못 쓰면 흔적 없이 동작한다
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null, expiresInSec = 900): void {
  accessToken = token;
  expiresAt = token ? Date.now() + expiresInSec * 1000 : 0;
  listeners.forEach((fn) => fn(token));
}

export function isAccessTokenFresh(skewMs = 30_000): boolean {
  return accessToken !== null && Date.now() < expiresAt - skewMs;
}

export function subscribeToken(fn: (token: string | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** 동시에 여러 요청이 401을 맞아도 refresh 는 한 번만 나간다 (rotation 재사용 탐지에 걸리지 않게). */
export function refreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  inflight ??= (async () => {
    try {
      await mockReady();
      const res = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        setAccessToken(null);
        if (res.status === 401) markSession(false);
        return null;
      }
      const data = (await res.json()) as TokenResponse;
      setAccessToken(data.access_token, data.expires_in);
      markSession(true);
      return data.access_token;
    } catch {
      setAccessToken(null);
      return null;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/**
 * 로그아웃은 절대 던지지 않는다: 네트워크가 끊겼든 서버가 거절했든 이 브라우저의 로그인 상태는 반드시 지운다.
 * 서버는 access token 이 만료됐거나 없어도 refresh 쿠키를 폐기한다(멱등). 서버까지 닿았는지는 반환값으로 알려 준다.
 */
export async function logout(): Promise<boolean> {
  const token = accessToken;
  // 응답을 기다리는 동안 다른 요청이 옛 토큰을 쓰지 않게 먼저 비운다
  setAccessToken(null);
  markSession(false);
  try {
    await mockReady();
    const res = await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * 아이디 · 비밀번호 로그인과 가입 (우리 DB 계정, 이메일 인증 없음 — 가입하면 바로 모든 기능).
 * 성공하면 API 가 access token 을 돌려주고 refresh 쿠키를 심는다 → OAuth 로 돌아왔을 때와 같은 상태가 된다.
 * 실패는 던지지 않고 ApiError 로 돌려준다(화면이 코드별로 문구를 고른다).
 */
export async function passwordAuth(
  mode: "login" | "signup",
  body: { login_id: string; password: string; nickname?: string },
): Promise<{ ok: true } | { ok: false; error: ApiError }> {
  await mockReady();
  let res: Response;
  try {
    res = await fetch(`${API_URL}/auth/${mode}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, error: await parseErrorResponse(new Response(null, { status: 503 })) };
  }
  if (!res.ok) return { ok: false, error: await parseErrorResponse(res) };
  const data = (await res.json()) as TokenResponse;
  setAccessToken(data.access_token, data.expires_in);
  markSession(true);
  return { ok: true };
}

/** API 는 `redirect_to`(웹 안의 상대 경로)를 읽는다. 로그인에 실패하면 `/login?error=…&next=…` 로 돌아온다. */
export function oauthLoginUrl(provider: "kakao" | "naver" | "google", redirectTo = "/my"): string {
  const url = new URL(`${API_URL}/auth/${provider}/login`);
  url.searchParams.set("redirect_to", redirectTo);
  return url.toString();
}
