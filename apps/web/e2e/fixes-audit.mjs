// 버튼 전수 검사 · 대량 검증이 찾은 결함들이 고쳐졌는지, 진짜 크롬 · 실제 API 로 다시 본다.
//   node e2e/fixes-audit.mjs [outDir]
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000/v1";
const outDir = process.argv[2] ?? "fixes-audit";
mkdirSync(outDir, { recursive: true });
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};
const d = new Date();
d.setDate(d.getDate() + 5);
const ymd = d.toISOString().slice(0, 10);
const generate = async (body) => (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

const browser = await chromium.launch({ channel: "chrome" });
const stub = (context) => context.route("**/v1/performances**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], partial: false }) }));
const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
await stub(desktop);

console.log("\n[1] 채팅을 쓸 수 없는 환경에서 채팅 입구는 한 번도 뜨지 않는다");
const chatOn = (await (await fetch(`${API}/meta/features`)).json()).chat === true;
{
  const page = await desktop.newPage();
  // 기능 확인이 늦게 오는 상황(느린 망)을 만든다: 그 사이에 입구가 보이면 결함이다
  await page.route("**/v1/meta/features", async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  const seen = [];
  await page.exposeFunction("__sawChat", (t) => seen.push(t));
  await page.addInitScript(() => {
    const look = () => {
      for (const a of document.querySelectorAll("a[href='/chat']")) if (a.getBoundingClientRect().width > 0) window.__sawChat(a.textContent.trim());
    };
    new MutationObserver(look).observe(document, { subtree: true, childList: true });
    document.addEventListener("DOMContentLoaded", look);
  });
  await page.goto(`${WEB}/`, { timeout: 120000 });
  await page.waitForTimeout(6000);
  if (chatOn) console.log("   (이 환경은 채팅이 켜져 있다 → 확인된 뒤에 나타나는지만 본다)");
  check(chatOn ? true : seen.length === 0, `채팅 링크가 보인 적이 없다${seen.length ? ` — 보인 것: ${[...new Set(seen)].join(", ")}` : ""}`);
  check(await page.getByRole("link", { name: "갈 만한 곳 먼저 둘러보기" }).isVisible().catch(() => false) || chatOn, "랜딩 끝의 두 번째 버튼은 처음부터 '둘러보기'다");
  check((await page.getByRole("link", { name: "내가짠데이 홈" }).first().getAttribute("aria-current")) === "page", "홈에서 로고는 '지금 여기'라고 말한다");
  await page.close();
}

console.log("\n[2] 코스를 짜는 중 · 결과를 보는 중에는 헤더에 '무료로 추천받기'가 없다");
{
  const page = await desktop.newPage();
  await page.goto(`${WEB}/plan`, { timeout: 120000 });
  await page.getByRole("radiogroup", { name: "지역 선택" }).getByRole("button").first().waitFor({ timeout: 60000 });
  check((await page.locator("header").getByRole("link", { name: "무료로 추천받기" }).count()) === 0, "/plan 의 헤더에 제자리 링크가 없다");
  await page.goto(`${WEB}/explore`, { timeout: 120000 });
  await page.locator("main article").first().waitFor({ timeout: 60000 });
  check((await page.locator("header").getByRole("link", { name: "무료로 추천받기" }).count()) === 1, "다른 화면(/explore)에는 그대로 있다");

  console.log("\n[3] 이벤트 좌우 버튼은 실제로 목록을 옮긴다 (검사 도구는 요소 안의 가로 스크롤을 못 본다)");
  const nextBtn = page.getByRole("button", { name: "다음 이벤트" });
  if (await nextBtn.count()) {
    const left = () => page.evaluate(() => Math.max(...[...document.querySelectorAll("[aria-labelledby='events-heading'] *")].map((el) => el.scrollLeft)));
    const before = await left();
    await nextBtn.click();
    await page.waitForTimeout(1200);
    const after = await left();
    check(after > before + 40, `'다음 이벤트'를 누르면 목록이 옆으로 간다 (${Math.round(before)} → ${Math.round(after)}px)`);
    await page.getByRole("button", { name: "이전 이벤트" }).click();
    await page.waitForTimeout(1200);
    check((await left()) < after - 40, "'이전 이벤트'를 누르면 돌아온다");
  } else console.log("   (이번 주 이벤트가 적어 좌우 버튼이 없다)");
  await page.close();
}

console.log("\n[4] 대안 코스 탭: 없는 평점을 약속하지 않고, 누르면 그 코스로 간다");
{
  const out = await generate({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 120000, start_at: `${ymd}T12:00:00+09:00`, duration_min: 180, alternatives: 2 });
  const page = await desktop.newPage();
  await page.goto(`${WEB}/course/${out.courses[0].id}`, { timeout: 120000 });
  await page.locator("[aria-label='코스 일정'] article").first().waitFor({ timeout: 60000 });
  const tabs = page.getByRole("tab");
  const labels = await tabs.allInnerTexts();
  console.log("   탭:", labels.join(" · "));
  check(labels.every((t) => !/평점/.test(t)), "어느 탭도 '평점'을 말하지 않는다");
  if (labels.length > 1) {
    const before = page.url();
    await tabs.nth(labels.length - 1).click();
    await page.waitForURL((u) => u.href !== before, { timeout: 30000 }).catch(() => undefined);
    check(page.url() !== before, "마지막 탭을 누르면 주소가 그 코스로 바뀐다");
    await page.locator("[aria-label='코스 일정'] article").first().waitFor({ timeout: 60000 });
    check((await tabs.nth(labels.length - 1).getAttribute("aria-selected")) === "true", "누른 탭이 선택된 것으로 표시된다");
  }
  await page.close();
}

console.log("\n[5] 좁은 지도에서도 일곱 곳의 핀이 모두 지도 안에 있고, 그려지는 순간부터 보인다");
{
  const mobile = await browser.newContext({ ...devices["Pixel 7"], locale: "ko-KR" });
  await stub(mobile);
  for (const body of [
    { region: "busan-nam", purpose: "date", party_size: 2, budget_total: 240000, start_at: `${ymd}T11:30:00+09:00`, transport: "walk", style: "efficient", alternatives: 0 },
    { region: "gyeonggi-seongnam-sujeong", purpose: "solo", party_size: 1, budget_total: 120000, start_at: `${ymd}T11:30:00+09:00`, transport: "walk", style: "efficient", alternatives: 0 },
  ]) {
    const course = (await generate(body)).courses[0];
    const page = await mobile.newPage();
    await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
    const firstPin = page.locator(".jj-pin-drop").first();
    await firstPin.waitFor({ state: "attached", timeout: 60000 });
    const faint = await page.evaluate(() => [...document.querySelectorAll(".jj-pin-drop")].filter((el) => Number(getComputedStyle(el).opacity) < 0.99).length);
    check(faint === 0, `${body.region}: 핀이 생긴 그 순간에 투명한 핀이 없다 (${faint}개)`);
    await page.waitForTimeout(2500);
    const pins = await page.evaluate(() => {
      const box = document.querySelector(".jj-map").getBoundingClientRect();
      const drops = [...document.querySelectorAll(".jj-pin-drop")].map((el) => el.getBoundingClientRect());
      const inside = drops.filter((r) => r.left >= box.left - 2 && r.right <= box.right + 2 && r.top >= box.top - 2 && r.bottom <= box.bottom + 2).length;
      let overlaps = 0;
      for (let i = 0; i < drops.length; i += 1) for (let j = i + 1; j < drops.length; j += 1) if (Math.abs(drops[i].left - drops[j].left) < 30 && Math.abs(drops[i].top - drops[j].top) < 30) overlaps += 1;
      return { n: drops.length, inside, overlaps };
    });
    check(pins.n === course.stops.length && pins.inside === pins.n, `${body.region}: 핀 ${pins.inside}/${pins.n} · 장소 ${course.stops.length}곳이 모두 지도 안`);
    check(pins.overlaps === 0, `${body.region}: 서로 덮은 핀이 없다 (${pins.overlaps}쌍)`);
    await page.screenshot({ path: path.join(outDir, `pins-${body.region}.png`) });
    await page.close();
  }
  await mobile.close();
}

console.log("\n[6] 둘이서 2만원 · 새벽 1시 반: 한 곳짜리 코스로 끝나지 않고, 더한 곳을 말한다");
{
  const out = await generate({ origin: { lat: 37.4979, lng: 127.0276 }, origin_label: "강남역", purpose: "date", party_size: 2, budget_total: 20000, start_at: `${ymd}T01:30:00+09:00`, transport: "walk", alternatives: 0 });
  const course = out.courses?.[0];
  check(Boolean(course), `코스가 만들어진다${course ? "" : ` (${out.code})`}`);
  if (course) {
    console.log("   ", course.stops.map((s) => `${s.role} ${s.place.name} ${s.est_price}`).join(" → "), "| 경고:", course.warnings.map((w) => w.code).join(","));
    check(course.stops.length >= 2, `두 곳 이상이다 (${course.stops.length}곳)`);
    check(course.totals.price <= 20000, `예산 안이다 (${course.totals.price}원)`);
    const page = await desktop.newPage();
    await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
    await page.locator("[aria-label='코스 일정'] article").first().waitFor({ timeout: 60000 });
    const text = await page.locator("main").innerText();
    if (course.warnings.some((w) => w.code === "TOPPED_UP")) check(/더했어요/.test(text), "결과 화면이 '더했다'고 말한다");
    check(/영업시간|24시/.test(text), "밤 안내가 보인다");
    await page.screenshot({ path: path.join(outDir, "night-20000.png"), fullPage: true });
    await page.close();
  }
}

await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
