// 둘러보기 점검: "전체 지역"에서도 유형 필터(공원 · 전시 …)가 비지 않고, 첫 화면이 한 가지 유형으로 도배되지 않는지.
//   node e2e/explore-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const outDir = process.argv[2] ?? "explore-audit";
mkdirSync(outDir, { recursive: true });
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
await page.goto(`${WEB}/explore`, { timeout: 120000 });
const cards = page.locator("main article");
await cards.first().waitFor({ timeout: 60000 });
const kinds = await page.evaluate(() => [...document.querySelectorAll("main article")].slice(0, 12).map((el) => el.querySelector("span.rounded-full")?.textContent?.trim()).filter(Boolean));
console.log("전체 탭 첫 12장:", kinds.join(" · "));
check(new Set(kinds).size >= 3, "전체 탭의 첫 화면에 세 가지 이상의 유형이 섞여 있다");

for (const label of ["공원", "전시", "문화공간", "관광지"]) {
  await page.getByRole("group", { name: "종류" }).getByRole("button", { name: label, exact: true }).click();
  await page.waitForTimeout(1800);
  const n = await cards.count();
  const names = await cards.locator("h3").allInnerTexts();
  console.log(`${label}: ${n}곳 — ${names.slice(0, 5).join(", ")}`);
  check(n > 0, `전체 지역 · ${label} 필터가 비어 있지 않다`);
  if (label === "공원") await page.screenshot({ path: path.join(outDir, "explore-parks.png") });
}
check(errors.length === 0, `페이지 에러 0건${errors.length ? " → " + errors[0] : ""}`);
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
