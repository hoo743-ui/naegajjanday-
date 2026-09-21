import { http, HttpResponse } from "msw";
import type { Me, Preferences, SavedCourse } from "@/lib/api/types";
import { listSaved, markSaved, MockProblem } from "../fixtures/course-engine";
import { purposes, regions } from "../fixtures/meta";
import { latency, paginate, problem, u } from "./utils";

/** 목 모드의 "로그아웃 상태" 플래그. 없으면 항상 목 관리자 계정으로 로그인돼 있다. */
const LOGGED_OUT_KEY = "njd_mock_logged_out";

function isLoggedOut(): boolean {
  try {
    return typeof sessionStorage !== "undefined" && sessionStorage.getItem(LOGGED_OUT_KEY) === "1";
  } catch {
    return false;
  }
}
function setLoggedOut(value: boolean) {
  try {
    if (typeof sessionStorage === "undefined") return;
    if (value) sessionStorage.setItem(LOGGED_OUT_KEY, "1");
    else sessionStorage.removeItem(LOGGED_OUT_KEY);
  } catch {
    // 시크릿 모드 등은 무시
  }
}

let me: Me = {
  id: "u_mock_admin",
  nickname: "짠이친구",
  email: "mock@naegajjanday.dev",
  avatar_url: null,
  role: "admin",
  provider: "kakao",
  created_at: "2026-03-02T10:00:00+09:00",
};

let preferences: Preferences = { liked_tags: ["조용한", "가성비"], disliked_tags: ["웨이팅"], transport: "walk" };

const unauthorized = () => problem(401, "UNAUTHORIZED", "로그인이 필요해요", "다시 로그인해 주세요.");

function requireAuth(request: Request) {
  return isLoggedOut() || !request.headers.get("authorization") ? unauthorized() : null;
}

export const userHandlers = [
  http.post(u("/auth/refresh"), async () => {
    await latency(120);
    if (isLoggedOut()) return unauthorized();
    return HttpResponse.json({ access_token: "mock-access", expires_in: 900 });
  }),

  http.post(u("/auth/logout"), () => {
    setLoggedOut(true);
    return new HttpResponse(null, { status: 204 });
  }),

  // 실제로는 OAuth 제공자로 302 된다. 목에서는 플래그만 지우고 끝낸다 (로그인 화면이 refresh 를 직접 부른다).
  http.get(u("/auth/:provider/login"), () => {
    setLoggedOut(false);
    return HttpResponse.json({ ok: true });
  }),

  http.get(u("/me"), async ({ request }) => {
    await latency(150);
    return requireAuth(request) ?? HttpResponse.json(me);
  }),

  http.patch(u("/me"), async ({ request }) => {
    await latency(300);
    const denied = requireAuth(request);
    if (denied) return denied;
    const body = (await request.json()) as Partial<Pick<Me, "nickname">>;
    const nickname = body.nickname?.trim();
    if (nickname !== undefined && (nickname.length < 2 || nickname.length > 12)) {
      return problem(422, "VALIDATION_ERROR", "닉네임을 확인해 주세요", "닉네임은 2~12자로 적어 주세요.");
    }
    me = { ...me, ...(nickname ? { nickname } : {}) };
    return HttpResponse.json(me);
  }),

  http.delete(u("/me"), async ({ request }) => {
    await latency(400);
    const denied = requireAuth(request);
    if (denied) return denied;
    setLoggedOut(true);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(u("/me/preferences"), async ({ request }) => {
    await latency(150);
    return requireAuth(request) ?? HttpResponse.json(preferences);
  }),

  http.put(u("/me/preferences"), async ({ request }) => {
    await latency(300);
    const denied = requireAuth(request);
    if (denied) return denied;
    preferences = { ...preferences, ...((await request.json()) as Preferences) };
    return HttpResponse.json(preferences);
  }),

  http.get(u("/me/courses"), async ({ request }) => {
    await latency(300);
    const denied = requireAuth(request);
    if (denied) return denied;
    const items: SavedCourse[] = listSaved()
      .map((s, i) => ({
        id: s.course.id,
        label: s.course.label,
        summary: s.course.summary,
        saved_at: new Date(Date.now() - i * 3_600_000).toISOString(),
        region_name: regions.find((r) => r.slug === s.regionSlug)?.name ?? null,
        purpose_name: purposes.find((p) => p.code === s.req.purpose)?.name ?? s.req.purpose,
        party_size: s.req.party_size,
        totals: {
          price: s.course.totals.price,
          budget_left: s.course.totals.budget_left,
          travel_min: s.course.totals.travel_min,
          duration_min: s.course.totals.duration_min,
        },
        stop_names: s.course.stops.map((st) => st.place.name),
        visited: false,
      }))
      .reverse();
    return HttpResponse.json(paginate(items, new URL(request.url), 20));
  }),

  http.delete(u("/me/courses/:id"), async ({ params, request }) => {
    await latency(300);
    const denied = requireAuth(request);
    if (denied) return denied;
    try {
      markSaved(String(params.id), false);
      return new HttpResponse(null, { status: 204 });
    } catch (error) {
      if (error instanceof MockProblem) return problem(error.status, error.code, error.message, error.detail);
      throw error;
    }
  }),
];
