import { expect, test as base, type Page } from "@playwright/test";

export const API_URL = (process.env.E2E_API_URL ?? "http://localhost:8000/v1").replace(/\/$/, "");

/**
 * 콘솔의 "Failed to load resource" 는 URL 이 없어 무엇이 실패했는지 알 수 없다 → 그 문구는 버리고,
 * 아래 response 리스너가 실패한 응답을 URL·상태코드와 함께 직접 잡는다(더 엄격하고 더 친절하다).
 */
const IGNORED = [/Failed to load resource/, /Download the React DevTools/];

/** 실패해도 정상인 응답. 나머지 4xx/5xx 는 전부 결함으로 본다. */
const EXPECTED_FAILURES: { url: RegExp; status: number[] }[] = [
  { url: /\/v1\/auth\/refresh$/, status: [401] }, // 익명 방문자의 로그인 확인
  { url: /\/v1\/me(\/|$)/, status: [401] },
  { url: /\/v1\/courses\/00000000-0000-4000-8000-000000000000/, status: [404] }, // "없는 코스" 테스트
  // 서드파티(지도 타일·사진·경로 서버)의 일시 실패는 우리 결함이 아니고, 화면은 폴백으로 동작해야 한다
  { url: /basemaps\.cartocdn\.com|tile\.openstreetmap\.org|wikimedia\.org|routing\.openstreetmap\.de/, status: [400, 403, 404, 429, 500, 502, 503, 504] },
];

interface Health {
  errors: string[];
}

/**
 * 모든 테스트에 공통으로 거는 건강 검사 — "사람이 눌러 봐야만 아는 버그"를 자동으로 잡는다.
 *  1) 콘솔 error / 처리되지 않은 예외 0
 *  2) 에러 바운더리("앗, 짠이가 실수했어요") 미노출
 *  3) 가로 스크롤 0 (어떤 뷰포트에서도 본문이 옆으로 넘치지 않는다)
 */
export const test = base.extend<{ health: Health }>({
  health: [
    async ({ page }, use) => {
      const health: Health = { errors: [] };
      page.on("console", (msg) => {
        if (msg.type() !== "error") return;
        const text = msg.text();
        if (!IGNORED.some((re) => re.test(text))) health.errors.push(text.slice(0, 300));
      });
      page.on("pageerror", (err) => health.errors.push(`uncaught exception: ${err.message.slice(0, 300)}`));
      page.on("response", (res) => {
        const status = res.status();
        if (status < 400) return;
        const url = res.url();
        if (EXPECTED_FAILURES.some((e) => e.url.test(url) && e.status.includes(status))) return;
        health.errors.push(`HTTP ${status} ${res.request().method()} ${url.slice(0, 160)}`);
      });
      await use(health);
      expect(health.errors, "콘솔 에러가 없어야 한다").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export async function expectHealthyLayout(page: Page) {
  await expect(page.getByText("INTERNAL_ERROR"), "에러 바운더리가 떠 있다").toHaveCount(0);
  const { overflow, offenders } = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const found: string[] = [];
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.right <= vw + 1) continue;
      // 가로 스크롤/클리핑 컨테이너 안쪽은 넘쳐도 본문을 밀지 않는다
      let parent = el.parentElement;
      let clipped = false;
      while (parent && parent !== document.body) {
        if (getComputedStyle(parent).overflowX !== "visible") {
          clipped = true;
          break;
        }
        parent = parent.parentElement;
      }
      if (!clipped) found.push(`<${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 60)}"> right=${Math.round(r.right)}/${vw} "${(el.textContent ?? "").trim().slice(0, 24)}"`);
    }
    return { overflow: document.documentElement.scrollWidth - vw, offenders: found.slice(0, 5) };
  });
  expect(overflow, `본문이 가로로 넘친다 — 범인: ${offenders.join(" | ") || "(찾지 못함)"}`).toBeLessThanOrEqual(1);
}

/** 장소가 실제로 있는 첫 지역 — 시드 DB 든 전국 DB 든 같은 테스트가 돈다 */
export async function firstPopulatedRegion(page: Page): Promise<{ slug: string; name: string }> {
  const res = await page.request.get(`${API_URL}/meta/regions`);
  expect(res.ok()).toBeTruthy();
  const { items } = (await res.json()) as { items: { slug: string; name: string; level: number; place_count: number }[] };
  const preferred = items.find((r) => r.slug === "seoul-hongdae" && r.place_count > 0);
  const region = preferred ?? items.filter((r) => r.place_count > 0).sort((a, b) => b.level - a.level)[0];
  expect(region, "장소가 있는 지역이 하나는 있어야 한다").toBeTruthy();
  return region!;
}

/** UI 를 거치지 않고 코스를 하나 만든다(결과 화면 테스트용). 낮 12시 출발로 고정해 영업시간 영향을 없앤다. */
export async function createCourse(page: Page, overrides: Record<string, unknown> = {}): Promise<string> {
  const region = await firstPopulatedRegion(page);
  const start = new Date();
  start.setDate(start.getDate() + 1);
  const startAt = `${start.toISOString().slice(0, 10)}T12:00:00+09:00`;
  const res = await page.request.post(`${API_URL}/courses/generate`, {
    data: { region: region.slug, purpose: "date", party_size: 2, budget_total: 80_000, start_at: startAt, ...overrides },
  });
  expect(res.ok(), `generate 실패: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = (await res.json()) as { courses: { id: string }[] };
  expect(body.courses.length).toBeGreaterThan(0);
  return body.courses[0]!.id;
}
