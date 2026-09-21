// 여행 일정의 하루를 다시 짜도 여행이 흩어지지 않는지: 1박 2일을 만들고 1일차 화면에서 "다시 짜기"를 눌러 본다.
// 가족 약속에 "술 한잔"을 고르면 결과 화면이 그 사실을 말하는지도 본다.
//   node e2e/trip-reroll-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "trip-reroll-audit";
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 5);
const day = d.toISOString().slice(0, 10);
const post = async (body) => (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

const trip = await post({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 240000, nights: 1, start_at: `${day}T13:00:00+09:00` });
const [one, two] = trip.courses;
console.log(`여행: ${trip.courses.map((c) => `${c.label} ${c.stops.length}곳`).join(" | ")}`);

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));

await page.goto(`${WEB}/course/${one.id}`, { timeout: 120000 });
await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
const before = (await page.locator("header p").first().innerText()).replace(/\s+/g, " ");
console.log("머리말:", before);
check(/1일차 \/ 2일/.test(before) && /여행 전체 240,000원/.test(before), "머리말에 일차와 여행 전체 예산이 보인다");
check((await page.getByRole("tablist", { name: "날짜별 코스" }).count()) === 1, "탭의 이름이 '날짜별 코스'다");

await page.getByRole("button", { name: "다른 장소들로 코스 다시 짜기" }).click();
await page.waitForURL((url) => url.pathname.startsWith("/course/") && !url.pathname.endsWith(one.id), { timeout: 120000 });
await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
const after = (await page.locator("header p").first().innerText()).replace(/\s+/g, " ");
const tabs = await page.getByRole("tab").allInnerTexts();
console.log("다시 짠 뒤 머리말:", after);
console.log("다시 짠 뒤 탭:", tabs.join(" | "));
check(/1일차 \/ 2일/.test(after), "다시 짠 코스도 여전히 1일차다");
check(tabs.length === 2 && tabs[0].includes("1일차") && tabs[1].includes("2일차"), "탭은 여전히 1일차 · 2일차 둘이다");
const newId = new URL(page.url()).pathname.split("/").pop();
const secondDay = await (await fetch(`${API}/courses/${two.id}`)).json();
check(JSON.stringify(secondDay.siblings.map((s) => s.id)) === JSON.stringify([newId, two.id]), "2일차에서 보는 탭도 새 1일차를 가리킨다");
await page.screenshot({ path: path.join(outDir, "trip-after-reroll.png") });

// 가족 + 술 한잔: 말없이 빼지 않는다
const family = await post({ region: "seoul-hongdae", purpose: "family", party_size: 3, budget_total: 180000, extras: ["BAR"], start_at: `${day}T15:00:00+09:00`, alternatives: 0 });
await page.goto(`${WEB}/course/${family.courses[0].id}`, { timeout: 120000 });
await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
const said = await page.getByRole("status").filter({ hasText: "술 한잔" }).allInnerTexts();
console.log("경고:", said.join(" / ") || "(없음)");
check(said.length > 0, "술 한잔을 못 넣었다고 결과 화면이 말한다");
const ratingBars = await page.getByText("리뷰 수로 보정한 평점").count();
check(ratingBars === 0, "자료가 없는 평점 막대는 그리지 않는다");

check(errors.length === 0, `페이지 에러 0건${errors.length ? " → " + errors[0] : ""}`);
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
