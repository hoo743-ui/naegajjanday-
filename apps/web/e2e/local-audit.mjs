// 동네 특색 점검: 명물이 뚜렷한 동네의 코스 화면과 위저드 취향 단계를 찍고, 명물을 눌러 다시 짜 본다.
//   node e2e/local-audit.mjs [outDir] [regionSlug]
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "local-audit";
const region = process.argv[3] ?? "sokcho-jungang";
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 3);
const res = await fetch(`${API}/courses/generate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ region, purpose: "family", party_size: 4, budget_total: 120000, start_at: `${d.toISOString().slice(0, 10)}T11:00:00+09:00`, duration_min: 360 }),
});
const body = await res.json();
const course = body.courses[0];
console.log("명물:", (body.local?.specialties ?? []).map((s) => `${s.word}×${s.count}`).join(", "));
console.log("코스:", course.stops.map((s) => `[${s.role}] ${s.place.name}`).join(" → "));

const browser = await chromium.launch({ channel: "chrome" });
for (const [tag, options] of [["desktop", { viewport: { width: 1440, height: 900 } }], ["mobile", devices["Pixel 7"]]]) {
  const context = await browser.newContext({ ...options, locale: "ko-KR" });
  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(String(e).slice(0, 160)));
  await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
  const card = page.getByRole("region", { name: /이런 동네예요/ });
  await card.waitFor({ timeout: 60000 });
  await card.scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  await card.screenshot({ path: path.join(outDir, `${tag}-local-card.png`) });
  console.log(`${tag} 카드:`, (await card.innerText()).replace(/\s+/g, " ").slice(0, 220));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(`${tag} 가로 넘침: ${overflow}px · 페이지 에러: ${problems.length}`);

  if (tag === "desktop") {
    // 두 번째 명물을 눌러 그걸 넣은 코스로 다시 짠다
    const chips = card.getByRole("button", { pressed: false });
    const word = (await chips.first().locator("b").innerText()).trim();
    await chips.first().click();
    await page.waitForURL((u) => !u.pathname.endsWith(course.id), { timeout: 90000 });
    const next = page.getByRole("region", { name: /이런 동네예요/ });
    await next.waitFor({ timeout: 60000 });
    const names = await page.getByLabel("코스 일정").getByRole("article").locator("h3").allInnerTexts();
    console.log(`'${word}' 로 다시 짠 코스:`, names.join(" → "));
    console.log("  카드 문구:", (await next.locator("p.text-blue-deep").innerText().catch(() => "(없음)")).replace(/\s+/g, " "));

    await page.goto(`${WEB}/plan?region=${region}&purpose=family`);
    for (let i = 0; i < 3; i += 1) {
      await page.getByRole("button", { name: "다음", exact: true }).click().catch(() => undefined);
      await page.waitForTimeout(700);
    }
    const pick = page.getByRole("radiogroup", { name: "꼭 넣을 동네 명물" });
    await pick.waitFor({ timeout: 30000 });
    await pick.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(outDir, "desktop-wizard-taste.png") });
    console.log("위저드 선택지:", (await pick.getByRole("radio").allInnerTexts()).map((t) => t.replace(/\s+/g, " ")).join(" | "));
  }
  await context.close();
}
await browser.close();
