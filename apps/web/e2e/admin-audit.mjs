// 관리자 화면을 실제 API 상대로 연다. 소셜 로그인 키가 없으므로, CLI 가 발급한 15분짜리 관리자 토큰을
// /auth/refresh 응답으로 끼워 넣어 "로그인된 상태"를 만든다. 그 밖의 모든 요청은 진짜 API 로 간다.
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const token = readFileSync(process.argv[2], "utf8").trim().split(/\r?\n/).pop().trim();
const out = process.argv[3];
const PAGES = ["/admin", "/admin/regions", "/admin/places", "/admin/attractions", "/admin/events", "/admin/banners", "/admin/scoring", "/admin/recommendations", "/admin/users"];

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
await context.route("**/v1/auth/refresh", (route) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: token, token_type: "Bearer", expires_in: 900 }) }),
);
const page = await context.newPage();
const problems = [];
let current = "";
page.on("pageerror", (e) => problems.push(`${current} pageerror: ${String(e).slice(0, 180)}`));
page.on("console", (m) => m.type() === "error" && !/401|favicon/.test(m.text()) && problems.push(`${current} console: ${m.text().slice(0, 180)}`));
page.on("response", (r) => r.status() >= 400 && r.url().includes("/v1/") && !r.url().includes("/auth/refresh") && problems.push(`${current} ${r.status()} ${r.url().split("/v1")[1].slice(0, 80)}`));

for (const path of PAGES) {
  current = path;
  await page.goto(`http://localhost:3000${path}`, { timeout: 120000 });
  await page.waitForTimeout(3500);
  const boundary = await page.getByText(/짠이가 실수했어요|문제가 생겼어요/).count();
  const h1 = (await page.locator("h1, h2").first().textContent().catch(() => ""))?.trim().slice(0, 40);
  const rows = await page.locator("table tbody tr").count();
  console.log(`${path.padEnd(24)} ${boundary ? "✗ 에러 화면" : "✓"}  제목: ${h1}  표 행: ${rows}`);
  await page.screenshot({ path: `${out}/admin${path.replace(/\//g, "_")}.png` });
}
console.log(problems.length ? "\n문제:\n" + [...new Set(problems)].join("\n") : "\n콘솔 에러 · 페이지 에러 · 실패 응답 없음");
await browser.close();
