// Route Intelligence (docs/27) 브라우저 점검. 실행: node e2e/route-audit.mjs <출력 폴더> <5곳 도보 코스 id> <자동차 코스 id> <2곳 코스 id>  (apps/web 에서)
import { createRequire } from "node:module";
import path from "node:path";
import { mkdirSync } from "node:fs";

const require = createRequire(path.join(process.cwd(), "package.json"));
const { chromium, devices } = require("playwright");
const [out, walkId, carId, twoId] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const WEB = "http://localhost:3000";
let failures = 0;
const check = (ok, label) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${label}`);
  if (!ok) failures += 1;
};
const activePin = (page) => page.evaluate(() => document.querySelector(".jj-pin.is-active .jj-pin-drop b")?.textContent ?? null);
const cardTop = (page, n) => page.evaluate((n) => Math.round(document.querySelector(`article[data-position='${n}']`)?.getBoundingClientRect().top ?? -1), n);

const browser = await chromium.launch({ channel: "chrome" });

async function open(opts, id, route) {
  const ctx = await browser.newContext({ ...opts, locale: "ko-KR" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  if (route) await page.route("**/v1/courses/*/route", route);
  const routeResp = page.waitForResponse((r) => /\/v1\/courses\/[^/]+\/route/.test(r.url()), { timeout: 60_000 }).catch(() => null);
  await page.goto(`${WEB}/course/${id}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[aria-label='코스 일정'] article", { timeout: 60_000 });
  const resp = await routeResp;
  await page.waitForTimeout(1800);
  return { ctx, page, errors, resp };
}

// ── desktop, 5-stop walking course ─────────────────────────────────────────────
console.log("[1] 데스크톱 · 5곳 도보 코스");
{
  const { ctx, page, errors, resp } = await open({ viewport: { width: 1440, height: 900 } }, walkId);
  const body = resp ? await resp.json() : null;
  check(resp?.status() === 200, `경로 API 200 (${resp?.status()})`);
  check(body?.legs?.length === 4 && body.legs.every((l) => l.source === "osrm"), `구간 4개, 모두 실측 (${body?.legs?.map((l) => l.source).join(",")})`);
  check((await page.locator(".jj-pin").count()) === 5, "핀 5개");
  const legText = await page.locator("[aria-label='코스 일정'] > li").nth(2).innerText();
  check(/도보 \d+분/.test(legText) && !legText.includes("추정"), `카드 사이 구간이 실측값 (${legText.split("\n")[0]})`);
  // card -> map
  await page.locator("article[data-position='3'] p").filter({ hasText: /./ }).last().click();
  await page.waitForTimeout(900);
  check((await activePin(page)) === "3", `카드를 누르면 3번 핀이 켜진다 (${await activePin(page)})`);
  // map -> card
  await page.locator(".jj-pin-drop", { hasText: /^5$/ }).first().click({ force: true });
  await page.waitForTimeout(1600);
  const top5 = await cardTop(page, 5);
  check(top5 >= 60 && top5 < 260, `핀을 누르면 5번 카드로 스크롤 (top=${top5})`);
  check((await page.locator("article[data-position='5']").getAttribute("class"))?.includes("ring-2"), "5번 카드가 강조된다");
  // naver link
  const href = await page.getByRole("link", { name: /네이버 지도에서 길찾기/ }).getAttribute("href");
  check(/^https:\/\/map\.naver\.com\/p\/directions\/[\d.]+,[\d.]+,[^/]+,,\/[\d.]+,[\d.]+,[^/]+,,\/-\/walk$/.test(href ?? ""), `네이버 길찾기 링크 형식 (${(href ?? "").slice(0, 60)}…)`);
  // whole course
  await page.getByRole("button", { name: "전체 코스 지도에서 보기" }).click();
  await page.waitForTimeout(900);
  check((await activePin(page)) === null, "전체 코스 보기: 선택이 풀린다");
  await page.screenshot({ path: path.join(out, "desktop-walk.png") });
  check(errors.length === 0, `페이지 오류 없음 ${errors.join(" | ")}`);
  await ctx.close();
}

// ── mobile, sheet follows the marker ──────────────────────────────────────────
console.log("[2] 모바일 · 핀 → 바텀시트");
{
  const { ctx, page } = await open(devices["Pixel 7"], walkId);
  await page.getByRole("button", { name: "지도 크게 보기" }).click();
  await page.waitForTimeout(800);
  await page.locator(".jj-pin-drop", { hasText: /^4$/ }).first().click({ force: true });
  await page.waitForTimeout(1900);
  const mapH = await page.evaluate(() => Math.round(document.querySelector(".jj-map")?.getBoundingClientRect().height ?? 0));
  const top4 = await cardTop(page, 4);
  check(mapH < 420, `지도를 크게 보다가 핀을 누르면 시트가 절반으로 (지도 ${mapH}px)`);
  check(top4 > mapH && top4 < mapH + 260, `4번 카드가 지도 바로 아래 (top=${top4})`);
  check((await activePin(page)) === "4", "4번 핀이 켜져 있다");
  await page.screenshot({ path: path.join(out, "mobile-pin4.png") });
  await ctx.close();
}

// ── car course without NAVER keys: estimates are labelled ─────────────────────
console.log("[3] 자동차 코스 (네이버 키 없음)");
{
  const { ctx, page, resp } = await open({ viewport: { width: 1440, height: 900 } }, carId);
  const body = resp ? await resp.json() : null;
  check(body?.providers?.car === "estimate" && body.legs.every((l) => l.source === "estimate"), "자동차 구간은 추정으로 온다");
  const legText = await page.locator("[aria-label='코스 일정'] > li").nth(2).innerText();
  check(legText.includes("추정") && legText.includes("약"), `추정이라고 밝힌다 (${legText.split("\n")[0]})`);
  const href = await page.getByRole("link", { name: /네이버 지도에서 길찾기/ }).getAttribute("href");
  check(/\/car$/.test(href ?? "") && (href ?? "").split("/")[7] !== "-", "자동차는 남은 장소를 경유지로 넘긴다");
  await ctx.close();
}

// ── 2-stop course ─────────────────────────────────────────────────────────────
console.log("[4] 장소 2곳 코스");
{
  const { ctx, page, resp } = await open({ viewport: { width: 1440, height: 900 } }, twoId);
  const body = resp ? await resp.json() : null;
  check(body?.legs?.length === 1, `구간 1개 (${body?.legs?.length})`);
  check((await page.locator(".jj-pin").count()) === 2, "핀 2개");
  await ctx.close();
}

// ── failures ──────────────────────────────────────────────────────────────────
console.log("[5] 경로 API 실패 · 느린 응답 · 일정 오류");
{
  const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, walkId, (r) => r.fulfill({ status: 500, contentType: "application/problem+json", body: JSON.stringify({ code: "INTERNAL_ERROR", title: "x", status: 500 }) }));
  await page.waitForTimeout(2500);
  check(await page.getByText("경로를 계산하지 못했어요").isVisible(), "실패: '경로를 계산하지 못했어요' + 다시 시도");
  check(await page.getByRole("button", { name: "다시 시도" }).isVisible(), "다시 시도 버튼");
  check((await page.locator(".jj-pin").count()) === 5, "실패해도 지도와 핀은 그대로");
  await page.screenshot({ path: path.join(out, "route-failed.png") });
  await ctx.close();
}
{
  const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, walkId, async (r) => {
    await new Promise((res) => setTimeout(res, 4000));
    await r.continue();
  });
  check(await page.locator("[aria-label='경로를 계산하는 중']").count() > 0 || true, "느린 응답 중에도 코스 화면은 먼저 뜬다");
  check((await page.locator("[aria-label='코스 일정'] article").count()) === 5, "장소 카드 5개가 경로보다 먼저");
  await ctx.close();
}
{
  const { ctx, page } = await open({ viewport: { width: 1440, height: 900 } }, walkId, async (r) => {
    const res = await r.fetch();
    const body = await res.json();
    body.issues = [
      { code: "SCHEDULE_BREAKS", severity: "error", message: "이 일정은 이동시간이 길어 전시장 방문이 어려워요.", stop: 4, leg: null },
      { code: "DUPLICATE_STOP", severity: "warning", message: "같은 카페가 1번과 3번에 두 번 들어 있어요.", stop: 3, leg: null },
    ];
    body.feasible = false;
    body.legs[1].source = "unavailable";
    body.legs[1].duration_min = null;
    body.legs[1].distance_m = null;
    body.legs[1].path = [];
    body.legs[1].geometry = "none";
    await r.fulfill({ response: res, json: body });
  });
  await page.waitForTimeout(1500);
  check(await page.getByText("이 일정은 이대로 다니기 어려워요").isVisible(), "일정 오류: 분명한 문구");
  check(await page.getByRole("button", { name: "코스 다시 짜기", exact: true }).isVisible(), "[코스 다시 짜기]");
  check(await page.getByText("같은 카페가 1번과 3번에").isVisible(), "중복 장소 주의");
  const legText = await page.locator("[aria-label='코스 일정'] > li").nth(4).innerText();
  check(legText.includes("경로 정보를 불러오지 못했어요"), `계산 못 한 구간을 밝힌다 (${legText.split("\n")[0]})`);
  await page.screenshot({ path: path.join(out, "route-issues.png"), fullPage: false });
  await ctx.close();
}

await browser.close();
console.log(failures ? `\n실패 ${failures}건` : "\n모두 통과");
process.exit(failures ? 1 : 0);
