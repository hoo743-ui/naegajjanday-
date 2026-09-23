// 거리뷰 점검: 코스의 각 장소에서 "가게 앞 거리뷰"를 열어 실제로 그려지는지(또는 "없어요"라고 말하는지) 본다.
//   node e2e/roadview-audit.mjs [outDir] [regionSlug]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "roadview-audit";
const region = process.argv[3] ?? "seoul-hongdae";
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 3);
const res = await fetch(`${API}/courses/generate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ region, purpose: "date", party_size: 2, budget_total: 70000, start_at: `${d.toISOString().slice(0, 10)}T18:00:00+09:00`, alternatives: 0 }),
});
const course = (await res.json()).courses[0];

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
const page = await context.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(String(e).slice(0, 160)));
await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
const cards = page.getByLabel("코스 일정").getByRole("article");
await cards.first().waitFor({ timeout: 60000 });
const count = await cards.count();
let shot = false; // 거리뷰가 실제로 그려진 첫 카드를 찍는다
for (let i = 0; i < count; i += 1) {
  const card = cards.nth(i);
  const name = (await card.getByRole("heading").first().innerText({ timeout: 3000 }).catch(() => "(이름 없음)")).trim();
  // 거리뷰는 "자세히" 안에 있다 (docs/33 §6)
  await card.getByRole("button", { name: /더보기$/ }).click().catch(() => {});
  await page.getByRole("menuitem", { name: /자세히 보기/ }).click().catch(() => {});
  await page.waitForTimeout(400);
  const button = card.getByRole("button", { name: "가게 앞 거리뷰" });
  if (!(await button.count())) {
    console.log(`${i + 1}. ${name}: 버튼 없음 (카카오 키 없음)`);
    continue;
  }
  await button.click();
  await page.waitForTimeout(4500);
  const drawn = await card.locator('[role="img"][aria-label$="거리뷰"] canvas, [role="img"][aria-label$="거리뷰"] img').count();
  const note = (await card.getByText(/거리뷰가 없어요|불러오지 못했어요|거리뷰 ⓒ Kakao/).first().innerText().catch(() => "")).slice(0, 40);
  console.log(`${i + 1}. ${name}: 그려진 요소 ${drawn} · ${note}`);
  if (drawn >= 2 && !shot) {
    shot = true;
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({ path: path.join(outDir, "stop-roadview.png") });
  }
}
console.log(`페이지 에러 ${problems.length}${problems.length ? " → " + problems[0] : ""}`);
await browser.close();
