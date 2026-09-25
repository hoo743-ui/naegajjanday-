import { defineConfig, devices } from "@playwright/test";

/**
 * E2E 는 목(MSW)이 아니라 **실제 API** 를 상대로 돈다 — 목 기준으로는 통과하지만 실제 응답과 어긋나는
 * 계약 불일치를 잡는 것이 이 테스트의 첫 번째 목적이다.
 *
 * 실행 전제: API(:8000)와 웹(:3000)이 떠 있을 것. (`docs/17-launch-readiness.md` 4-2)
 *   E2E_BASE_URL / E2E_API_URL 로 스테이징을 가리킬 수 있다.
 * 브라우저는 내려받지 않고 설치된 Chrome 을 쓴다(E2E_CHANNEL=msedge 로 바꿀 수 있다).
 */
const channel = process.env.E2E_CHANNEL ?? "chrome";
const SCREENS = /screens\.spec\.ts$/;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000, // dev 서버는 라우트를 처음 열 때 컴파일한다
  expect: { timeout: 15_000 },
  fullyParallel: false, // 코스 생성은 레이트리밋(익명 10회/시간)이 있다 → 직렬
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", testIgnore: SCREENS, use: { ...devices["Desktop Chrome"], channel, viewport: { width: 1440, height: 900 } } },
    { name: "tablet", testIgnore: SCREENS, use: { ...devices["Desktop Chrome"], channel, viewport: { width: 768, height: 1024 } } },
    { name: "mobile", testIgnore: SCREENS, use: { ...devices["Pixel 7"], channel } },
    // 판정 없이 390px 화면 사진만 찍는다 (e2e/screens.spec.ts, CI 아티팩트 mobile-screens)
    { name: "screens", testMatch: SCREENS, use: { ...devices["Desktop Chrome"], channel } },
  ],
});
