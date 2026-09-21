// 장소 상세 · 예산 도구 · 비 오는 날 점검: 묻혀 있던 데이터(조사된 메뉴 · 사진 · 개업 연도 · 공적 표식)가 화면에 나오는지 본다.
//   node e2e/place-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "place-audit";
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 3);
const day = d.toISOString().slice(0, 10);
const post = async (body) => (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

// 알뜰 예산: 착한가격업소(조사된 메뉴판 가격)가 코스에 들어오기 쉽다
const base = { region: "seoul-hongdae", purpose: "friends", party_size: 3, budget_total: 60000, start_at: `${day}T12:00:00+09:00`, alternatives: 0 };
const course = (await post(base)).courses[0];
const wet = (await post({ ...base, conditions: ["rain"] })).courses[0];
console.log("맑은 날:", course.stops.map((s) => `${s.role}:${s.place.name}`).join(" → "));
console.log("비 오는 날:", wet.stops.map((s) => `${s.role}:${s.place.name}`).join(" → "));

// API: 코스에 들어온 장소들의 상세에 무엇이 실려 오는지
for (const s of course.stops) {
  const p = await (await fetch(`${API}/places/${s.place.id}`)).json();
  console.log(`  ${s.place.name}: 메뉴 ${p.menus?.length ?? 0} · 사진 ${p.images?.length ?? 0} · 전화 ${p.phone ? "O" : "-"} · 영업시간 ${p.opening_hours?.length ?? 0} · 개업 ${p.since_year ?? "-"} · 업태 ${p.licensed_as ?? "-"} · 표식 ${(p.marks ?? []).map((m) => m.tag).join("/") || "-"}`);
}

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" })).newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(String(e).slice(0, 160)));
await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
const cards = page.getByLabel("코스 일정").getByRole("article");
await cards.first().waitFor({ timeout: 60000 });

// 가장 정보가 많은 장소의 시트를 연다
let opened = false;
for (let i = 0; i < (await cards.count()) && !opened; i += 1) {
  const button = cards.nth(i).locator("h3 button");
  if (!(await button.count())) continue;
  await button.click();
  const sheet = page.getByRole("dialog");
  await sheet.waitFor({ timeout: 20000 });
  await page.waitForTimeout(2500);
  const text = (await sheet.innerText()).replace(/\s+/g, " ");
  console.log(`시트[${i + 1}]:`, text.slice(0, 330));
  if (/조사된 메뉴판 가격|년째 영업|지정|관광공사/.test(text)) {
    await sheet.screenshot({ path: path.join(outDir, "place-sheet.png") });
    opened = true;
  }
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
}

// 예산 what-if 와 정산 문구
const tools = page.getByRole("region", { name: "예산 도구" });
await tools.scrollIntoViewIfNeeded();
await tools.getByRole("button", { name: /더$/ }).click();
await tools.getByText(/예산 .*이면/).waitFor({ timeout: 60000 });
console.log("what-if:", (await tools.innerText()).replace(/\s+/g, " ").slice(0, 300));
await tools.screenshot({ path: path.join(outDir, "budget-tools.png") });
await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
await tools.getByRole("button", { name: /정산 문구 복사|영수증 문구 복사/ }).click();
await page.waitForTimeout(600);
console.log("정산 문구:\n" + (await page.evaluate(() => navigator.clipboard.readText())).split("\n").map((l) => "   " + l).join("\n"));
console.log(`페이지 에러 ${problems.length}${problems.length ? " → " + problems[0] : ""}`);
await browser.close();
