import { NextResponse, type NextRequest } from "next/server";

/**
 * /my, /admin 미들웨어.
 *
 * 여기서는 로그인 여부를 판단하지 않는다. refresh 토큰은 API 가 **API 호스트에 Path=/v1/auth 로** 심는
 * HttpOnly 쿠키 `rt` 라서, 브라우저는 그 쿠키를 웹 서버(이 미들웨어)로 절대 보내지 않는다. 예전처럼
 * "쿠키가 없으면 /login 으로" 돌려보내면 로그인한 사람도 /my ↔ /login 을 끝없이 오간다.
 *
 * 가드는 두 겹으로 남아 있다.
 *  1) 화면: MyView · AdminShell 이 AuthProvider(POST /auth/refresh 로 세션 복원)의 상태를 보고
 *     비로그인이면 `/login?next=…` 로 보낸다.
 *  2) 데이터: /me · /admin/* 는 API 가 401/403 으로 막는다. 화면 코드가 새어 나가도 데이터는 안 나간다.
 *
 * 미들웨어는 보호 구역 응답에 "검색엔진 색인 금지"만 붙인다.
 */
export const PROTECTED_PREFIXES = ["/my", "/admin"] as const;

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function authMiddleware(request: NextRequest): NextResponse {
  const response = NextResponse.next();
  if (isProtectedPath(request.nextUrl.pathname)) response.headers.set("X-Robots-Tag", "noindex, nofollow");
  return response;
}
