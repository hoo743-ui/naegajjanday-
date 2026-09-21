// 시 · 도 전체를 고른 여행: 도시 중심 한 점이 아니라 사람들이 실제로 가는 구역을 도는지, 화면이 그 구역을 말하는지,
// 다시 짜도 도시 여행으로 남는지.
//   node e2e/city-trip-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "city-trip-audit";
mkdirSync(outDir, { recursive: true });
const d = new Date();
d.setDate(d.getDate() + 6);
const day = d.toISOString().slice(0, 10);
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};
const km = (a, b) => Math.hypot((a.lat - b.lat) * 111, (a.lng - b.lng) * 88);

const started = Date.now();
const res = await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ region: "busan", purpose: "travel", party_size: 2, budget_total: 300000, nights: 1, transport: "transit", start_at: `${day}T11:00:00+09:00` }) });
const made = await res.json();
check(res.ok, `부산 전체 1박 2일이 만들어진다 (${((Date.now() - started) / 1000).toFixed(1)}초)`);
check(Date.now() - started < 30000, "30초 안에 만들어진다 (예전에는 5분을 넘겼다)");
const regions = (await (await fetch(`${API}/meta/regions`)).json()).items;
const centre = regions.find((r) => r.slug === "busan").center;
for (const course of made.courses) {
  const far = Math.max(...course.stops.map((s) => km(centre, s.place)));
  console.log(`  ${course.label}: ${course.stops.map((s) => s.place.name).join(" → ")}`);
  check(far > 3, `${course.label}: 도시 중심 3km 밖으로 나간다 (가장 먼 곳 ${far.toFixed(1)}km)`);
}

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
await page.goto(`${WEB}/course/${made.courses[0].id}`, { timeout: 120000 });
await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
await page.waitForTimeout(3000);
const head = (await page.locator("header p").first().innerText()).replace(/\s+/g, " ");
console.log("  머리말:", head);
check(head.includes("부산") && head.includes("주변") && /1일차 \/ 2일/.test(head), "머리말이 도시 · 구역 · 일차를 말한다");
const pins = await page.locator(".jj-pin-drop").count();
check(pins === made.courses[0].stops.length, `모든 핀(${pins}개)이 지도에 있다`);
await page.screenshot({ path: path.join(outDir, "city-trip-day1.png") });

await page.getByRole("button", { name: "다른 장소들로 코스 다시 짜기" }).click();
await page.waitForURL((url) => !url.pathname.endsWith(made.courses[0].id), { timeout: 120000 });
await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
const again = (await page.locator("header p").first().innerText()).replace(/\s+/g, " ");
console.log("  다시 짠 뒤:", again);
check(again.includes("부산") && /1일차 \/ 2일/.test(again), "다시 짜도 부산 여행의 1일차로 남는다");
check(errors.length === 0, `페이지 에러 0건${errors.length ? " → " + errors[0] : ""}`);
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
