// 동 단위 지역 점검: 구를 열면 동이 나오고, 이름으로 찾아지고, 고르면 "사람들이 많이 가는 곳"이 뜨고,
// 그중 하나를 누르면 상세가 열리고, 그 동으로 코스가 실제로 만들어지는지. 진짜 크롬 · 실제 API 로 본다.
//   node e2e/dong-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const outDir = process.argv[2] ?? "dong-audit";
mkdirSync(outDir, { recursive: true });
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
// 공연 조회는 17초가 걸리고 이 점검의 대상이 아니다
await context.route("**/v1/performances**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], partial: false }) }));
const page = await context.newPage();
const errors = [];
const bad = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
page.on("response", (r) => r.status() >= 400 && /\/v1\//.test(r.url()) && !/auth\/refresh|\/me\b/.test(r.url()) && bad.push(`${r.status()} ${r.url().split("/v1")[1]}`));

await page.goto(`${WEB}/plan`, { timeout: 120000 });
const picker = page.getByRole("radiogroup", { name: "지역 선택" });
await picker.getByRole("button").first().waitFor({ timeout: 60000 });

console.log("\n[1] 구를 열면 동이 나온다");
await picker.getByRole("button", { name: /^서울.* 안으로 들어가기/ }).click();
await picker.getByRole("button", { name: /^성동구 안으로 들어가기/ }).click();
const dongHeading = page.getByText(/동네까지 좁히기 · 성동구의 동 \d+곳/);
await dongHeading.waitFor({ timeout: 30000 }).catch(() => undefined);
check(await dongHeading.isVisible(), "성동구 안에 '동네까지 좁히기' 구역이 보인다");
check(await picker.getByRole("radio", { name: /성동구 전체/ }).isVisible(), "'성동구 전체'도 그대로 고를 수 있다");
const dong = picker.getByRole("radio", { name: /^성수동/ });
check((await dong.count()) === 1, "성수동이 한 번 나온다");
check(await page.locator("nav[aria-label='지역 단계'] [aria-current='location']").innerText().then((t) => t.trim() === "성동구"), "지금 단계(성동구)가 aria-current 로 표시된다");
await page.screenshot({ path: path.join(outDir, "1-district-open.png"), fullPage: true });

console.log("\n[2] 동을 고르면 사람들이 많이 가는 곳이 뜨고, 누르면 상세가 열린다");
await dong.click();
check((await dong.getAttribute("aria-checked")) === "true", "성수동이 선택된 것으로 표시된다");
const hot = page.getByRole("region", { name: /에서 사람들이 많이 가는 곳/ });
await hot.waitFor({ timeout: 30000 }).catch(() => undefined);
check(await hot.isVisible(), "'사람들이 많이 가는 곳' 카드가 보인다");
const hotButtons = hot.getByRole("button", { name: /자세히 보기$/ });
const hotCount = await hotButtons.count();
check(hotCount >= 3, `많이 가는 곳이 3곳 이상이다 (${hotCount}곳)`);
check(/성수동/.test(await hot.getByRole("heading").innerText()), "순위의 범위가 구 전체가 아니라 성수동이다");
check(/티맵|내비게이션/.test(await hot.innerText()), "자료 출처를 적었다");
const firstName = hotCount ? (await hotButtons.first().getAttribute("aria-label")).replace(/ 자세히 보기$/, "") : "";
if (hotCount) {
  await hotButtons.first().click();
  const sheet = page.getByRole("dialog");
  await sheet.waitFor({ timeout: 20000 }).catch(() => undefined);
  check(await sheet.isVisible(), "누르면 상세 시트가 열린다");
  check((await sheet.getByRole("heading").first().innerText()).trim() === firstName, `시트의 제목이 누른 곳이다 (${firstName})`);
  await page.waitForTimeout(2500); // 상세(사진 · 영업시간 · 표식)가 도착할 시간
  await page.screenshot({ path: path.join(outDir, "2-hot-place-sheet.png") });
  await page.keyboard.press("Escape");
  await sheet.waitFor({ state: "hidden", timeout: 10000 }).catch(() => undefined);
  check(!(await sheet.isVisible()), "Esc 로 닫힌다");
}
await page.screenshot({ path: path.join(outDir, "2-dong-picked.png"), fullPage: true });

console.log("\n[3] 그 동으로 코스가 만들어진다");
await page.getByRole("button", { name: "다음", exact: true }).click();
await page.getByText("데이트", { exact: false }).first().click();
for (let i = 0; i < 2; i += 1) {
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "다음", exact: true }).click();
}
await page.waitForTimeout(700);
await page.getByRole("button", { name: "코스 짜 주세요" }).click();
await page.waitForURL(/\/course\//, { timeout: 180000 }).catch(() => undefined);
check(/\/course\//.test(page.url()), "코스 결과 화면으로 넘어갔다");
const stops = page.locator("[aria-label='코스 일정'] article");
await stops.first().waitFor({ timeout: 60000 }).catch(() => undefined);
const stopCount = await stops.count();
check(stopCount >= 2, `장소가 2곳 이상이다 (${stopCount}곳)`);
check(/성수동/.test(await page.locator("main").innerText()), "결과 화면이 '성수동'이라고 말한다 (slug 가 아니라)");
check(!/seoul-seongdong-d/.test(await page.locator("main").innerText()), "화면 어디에도 slug 가 새지 않는다");
await page.screenshot({ path: path.join(outDir, "3-course.png"), fullPage: true });

console.log("\n[4] 동 이름으로 찾아진다 (서울 밖)");
await page.goto(`${WEB}/plan`, { timeout: 120000 });
await picker.getByRole("button").first().waitFor({ timeout: 60000 });
await page.getByRole("searchbox").fill("광안");
const found = picker.getByRole("radio", { name: /^광안동/ });
await found.first().waitFor({ timeout: 30000 }).catch(() => undefined);
check((await found.count()) >= 1, "'광안'으로 광안동이 찾아진다");
if (await found.count()) {
  await found.first().click();
  const hot2 = page.getByRole("region", { name: /에서 사람들이 많이 가는 곳/ });
  await hot2.waitFor({ timeout: 30000 }).catch(() => undefined);
  check(await hot2.isVisible(), "광안동에서도 많이 가는 곳이 뜬다");
  console.log("   ", (await hot2.getByRole("button").allInnerTexts()).map((t) => t.split("\n")[0]).join(" · "));
}
await page.screenshot({ path: path.join(outDir, "4-search.png"), fullPage: true });

check(errors.length === 0, `페이지 에러가 없다${errors.length ? `: ${errors[0]}` : ""}`);
check(bad.length === 0, `실패한 API 요청이 없다${bad.length ? `: ${bad.slice(0, 3).join(" | ")}` : ""}`);
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
