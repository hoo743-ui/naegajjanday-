// 여행 일정 · 복수 선택 점검: 1박 2일 코스를 만들어 1일차 화면(숙소 카드 · 동네 이동 구간)을 찍고, 위저드의 새 선택지를 확인한다.
//   node e2e/trip-audit.mjs [outDir]
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "trip-audit";
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 4);
const day = d.toISOString().slice(0, 10);
const post = async (body) => (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

const trip = await post({ regions: ["gangneung-downtown", "sokcho-jungang"], purpose: "travel", purposes: ["date"], party_size: 2, budget_total: 300000, nights: 1, start_at: `${day}T13:00:00+09:00` });
const hop = await post({ regions: ["seoul-hongdae", "seoul-seongsu"], purpose: "friends", party_size: 3, budget_total: 150000, start_at: `${day}T12:00:00+09:00`, duration_min: 420 });
console.log("여행:", trip.courses.map((c) => `${c.label} ${c.totals.price.toLocaleString()}원 ${c.stops.length}곳`).join(" | "));

const browser = await chromium.launch({ channel: "chrome" });
for (const [tag, options] of [["desktop", { viewport: { width: 1440, height: 900 } }], ["mobile", devices["Pixel 7"]]]) {
  const context = await browser.newContext({ ...options, locale: "ko-KR" });
  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(String(e).slice(0, 160)));

  await page.goto(`${WEB}/course/${trip.courses[0].id}`, { timeout: 120000 });
  await page.getByLabel("코스 일정").waitFor({ timeout: 60000 });
  console.log(`${tag} 머리말:`, (await page.locator("header p").first().innerText()).replace(/\s+/g, " "));
  console.log(`${tag} 탭:`, (await page.getByRole("tab").allInnerTexts()).join(" | "));
  const stay = page.getByRole("region", { name: /이 근처에서 묵는다면/ });
  await stay.waitFor({ timeout: 30000 });
  await stay.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1200);
  await stay.screenshot({ path: path.join(outDir, `${tag}-stay-card.png`) });
  console.log(`${tag} 숙소 카드:`, (await stay.innerText()).replace(/\s+/g, " ").slice(0, 260));

  await page.goto(`${WEB}/course/${hop.courses[0].id}`, { timeout: 120000 });
  await page.getByLabel("코스 일정").waitFor({ timeout: 60000 });
  const legs = await page.getByLabel("코스 일정").locator("li[aria-label]").allInnerTexts();
  console.log(`${tag} 동네 이동 구간:`, legs.map((t) => t.replace(/\s+/g, " ")).filter((t) => t.includes("(으)로")).join(" / ") || "(없음)");
  console.log(`${tag} 머리말:`, (await page.locator("header p").first().innerText()).replace(/\s+/g, " "));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(`${tag} 가로 넘침 ${overflow}px · 페이지 에러 ${problems.length}${problems.length ? " → " + problems[0] : ""}`);

  if (tag === "desktop") {
    await page.goto(`${WEB}/plan?region=seoul-hongdae&purpose=date`);
    await page.waitForTimeout(1500);
    await page.getByRole("button", { name: /이어 다른 동네도 들르기/ }).waitFor({ timeout: 20000 });
    await page.screenshot({ path: path.join(outDir, "desktop-wizard-region.png") });
    await page.getByRole("button", { name: "다음", exact: true }).click();
    await page.waitForTimeout(900);
    console.log("위저드 함께 고를 목적:", (await page.getByRole("group", { name: "함께 고를 목적" }).getByRole("button").allInnerTexts()).join(" | "));
    await page.getByRole("button", { name: "다음", exact: true }).click();
    await page.waitForTimeout(900);
    console.log("위저드 일정 길이:", (await page.getByRole("radiogroup", { name: "일정 길이" }).getByRole("radio").allInnerTexts()).join(" | "));
    await page.getByRole("radio", { name: "1박 2일" }).click();
    await page.getByRole("region", { name: "며칠 일정인가요?" }).screenshot({ path: path.join(outDir, "desktop-wizard-nights.png") });
    await page.getByRole("button", { name: "다음", exact: true }).click();
    await page.waitForTimeout(900);
    console.log("위저드 야구 옵션:", await page.getByText("야구 보러 가요", { exact: true }).count());
  }
  await context.close();
}
await browser.close();
