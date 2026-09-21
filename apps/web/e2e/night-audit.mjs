// 밤·새벽 코스 점검: 새벽 2시 출발(도보) · 밤 11시 출발(차)로 실제 코스를 만들어 결과 화면을 연다.
// 코스가 비지 않고, "영업시간을 추정했다"는 안내가 보이고, 페이지 에러가 없어야 한다.
//   node e2e/night-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] ?? "night-audit";
mkdirSync(outDir, { recursive: true });
const d = new Date();
d.setDate(d.getDate() + 3);
const day = d.toISOString().slice(0, 10);
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

const CASES = [
  { tag: "walk-0200", body: { region: "seoul-hongdae", purpose: "friends", party_size: 2, budget_total: 80000, start_at: `${day}T02:00:00+09:00`, alternatives: 0 } },
  { tag: "car-2300", body: { region: "gangneung-downtown", purpose: "date", party_size: 2, budget_total: 100000, transport: "car", start_at: `${day}T23:00:00+09:00`, alternatives: 0 } },
];
const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
for (const { tag, body } of CASES) {
  const res = await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  check(res.ok, `${tag}: 코스가 만들어진다 (HTTP ${res.status})`);
  if (!res.ok) continue;
  const course = (await res.json()).courses[0];
  console.log(`  ${tag}: ${course.stops.map((s) => `${s.role} ${s.place.name}`).join(" → ")}`);
  check(course.stops.length >= 2, `${tag}: 두 곳 이상 들른다`);
  await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
  await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 });
  check((await page.getByRole("status").filter({ hasText: "가기 전에 영업 여부" }).count()) > 0, `${tag}: 결과 화면이 영업시간을 추정했다고 말한다`);
  await page.waitForTimeout(3500); // 지도 타일과 화면 맞춤이 끝난 뒤에 찍는다
  const pins = await page.locator(".jj-pin-drop").count();
  check(pins === course.stops.length, `${tag}: 지도에 핀 ${course.stops.length}개가 모두 있다 (${pins}개)`);
  await page.screenshot({ path: path.join(outDir, `${tag}.png`) });
}
check(errors.length === 0, `페이지 에러 0건${errors.length ? " → " + errors[0] : ""}`);
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
