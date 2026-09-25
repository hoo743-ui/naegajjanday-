import { test } from "@playwright/test";
import { createCourse } from "./fixtures";

/**
 * 휴대폰(390px) 화면 사진 — 판정은 하지 않고 찍기만 한다. CI 는 이 사진들을 아티팩트
 * `mobile-screens` 로 올려서, 푸시마다 사람이 화면을 눈으로 볼 수 있게 한다(docs/56).
 * 판정(콘솔 에러 · 가로 넘침 · 계약)은 journey.spec.ts 가 한다.
 */
const OUT = process.env.E2E_SCREENS_DIR ?? "e2e-screens";

test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });

async function shot(page: import("@playwright/test").Page, name: string) {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(600); // 등장 모션이 끝나기를 기다린다
  // 첫 화면 그대로(고정 하단 바가 제자리에 있다) + 페이지 전체
  await page.screenshot({ path: `${OUT}/${name}.png` });
  await page.screenshot({ path: `${OUT}/${name}-full.png`, fullPage: true });
}

test("홈", async ({ page }) => {
  await page.goto("/home");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await shot(page, "01-home");
});

test("위저드", async ({ page }) => {
  await page.goto("/plan");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await shot(page, "02-wizard-where");
});

test("결과 화면", async ({ page }) => {
  const id = await createCourse(page);
  await page.goto(`/course/${id}`);
  await page.getByLabel("코스 일정").waitFor();
  await shot(page, "03-course-result");
});
