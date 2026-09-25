// 배포 직전 점검 (docs/28): 실제 사용자 여정 네 개를 진짜 크롬 · 실제 API 로 끝까지 돌린다.
//   node e2e/release-audit.mjs [출력 폴더]     (apps/web 에서, API :8000 · 웹 :3000 이 떠 있을 때)
// 여정마다: 멈춘 곳 · 기다린 시간 · 콘솔 오류/경고 · 실패한 요청 · 가로 넘침 · 금액이 서로 맞는지(장소 합 = 영수증 = API).
import { createRequire } from "node:module";
import path from "node:path";
import { mkdirSync, writeFileSync } from "node:fs";

const require = createRequire(path.join(process.cwd(), "package.json"));
const { chromium, devices } = require("playwright");
const OUT = process.argv[2] ?? "release-audit";
mkdirSync(OUT, { recursive: true });
const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";

const VIEWPORTS = {
  "1440": { viewport: { width: 1440, height: 900 } },
  "1280": { viewport: { width: 1280, height: 800 } },
  "1024": { viewport: { width: 1024, height: 768 } },
  "768": { viewport: { width: 768, height: 1024 } },
  "430": { viewport: { width: 430, height: 932 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true },
  "390": { ...devices["iPhone 13"] },
};
// 알려진 소음: 카카오 SDK 가 스스로 남기는 로그 · 개발 모드 안내
const IGNORE = [/Download the React DevTools/, /\[Fast Refresh\]/, /image loading error/, /\[HMR\]/];

const report = { flows: [], overflow: [], console: [], network: [], money: [], findings: [] };
const note = (flow, ok, text) => {
  console.log(`${ok ? "  ✓" : "  ✗"} [${flow}] ${text}`);
  if (!ok) report.findings.push(`[${flow}] ${text}`);
};

/** creator: 코스를 만든 브라우저의 저장소(편집 키 · 세션 흔적)를 이어받는다 — 없으면 '다른 사람' */
let creatorState;
async function context(browser, vp, creator = false) {
  const ctx = await browser.newContext({ ...VIEWPORTS[vp], locale: "ko-KR", timezoneId: "Asia/Seoul", permissions: ["clipboard-read", "clipboard-write"], ...(creator && creatorState ? { storageState: creatorState } : {}) });
  return ctx;
}

function watch(page, flow) {
  page.on("console", (m) => {
    if (!["error", "warning"].includes(m.type())) return;
    const text = m.text();
    if (IGNORE.some((re) => re.test(text))) return;
    report.console.push({ flow, type: m.type(), text: text.slice(0, 240), url: page.url() });
  });
  page.on("pageerror", (e) => report.console.push({ flow, type: "pageerror", text: String(e).slice(0, 240), url: page.url() }));
  page.on("response", (r) => {
    const u = r.url();
    if (r.status() >= 400 && (u.startsWith(API) || u.startsWith(WEB))) report.network.push({ flow, status: r.status(), url: u.replace(API, "API").slice(0, 160) });
  });
  page.on("requestfailed", (r) => {
    const u = r.url();
    if ((u.startsWith(API) || u.startsWith(WEB)) && !/_next\/webpack-hmr|hot-update/.test(u)) report.network.push({ flow, status: "failed", url: u.replace(API, "API").slice(0, 160), error: r.failure()?.errorText });
  });
}

const overflowOf = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const wonToNum = (s) => Number(String(s).replace(/[^0-9]/g, ""));

async function wizard(page, flow) {
  const t0 = Date.now();
  await page.goto(`${WEB}/`, { waitUntil: "domcontentloaded" });
  await page.getByRole("link", { name: /이 조건으로 코스 짜기/ }).first().click();
  await page.waitForURL(/\/plan/);
  await page.getByRole("heading", { level: 1 }).waitFor();
  // 1. 지역: 많이 찾는 동네에서 홍대입구
  await page.getByRole("radio", { name: /홍대입구/ }).first().click().catch(async () => page.getByText("홍대입구", { exact: true }).first().click());
  await page.getByRole("button", { name: /^다음/ }).click();
  // 2. 목적: 데이트
  await page.getByRole("radio", { name: /데이트/ }).first().click().catch(async () => page.getByText("데이트", { exact: true }).first().click());
  await page.getByRole("button", { name: /^다음/ }).click();
  // 3. 인원 · 예산 · 시간 (기본값 그대로)
  await page.getByRole("button", { name: /^다음/ }).click();
  // 4. 취향 → 코스 짜 주세요
  const g0 = Date.now();
  await page.getByRole("button", { name: /코스 짜 주세요/ }).click();
  await page.waitForURL(/\/course\//, { timeout: 60_000 });
  await page.waitForSelector("[aria-label='코스 일정'] article", { timeout: 60_000 });
  const genMs = Date.now() - g0;
  note(flow, true, `위저드 4단계 → 결과 (전체 ${Math.round((Date.now() - t0) / 1000)}초, 코스 생성 대기 ${(genMs / 1000).toFixed(1)}초)`);
  return page.url().split("/course/")[1];
}

async function moneyCheck(page, flow, id) {
  const res = await (await fetch(`${API}/courses/${id}`)).json();
  const course = res.course ?? res;
  const budget = (res.request ?? {}).budget_total;
  const sum = course.stops.reduce((s, x) => s + x.est_price, 0);
  const receipt = page.locator("[aria-label='예산 사용 현황']");
  const totalText = await receipt.locator("dt:has-text('합계') + dd, dt:has-text('예상 합계') + dd").first().innerText().catch(() => "");
  const leftText = await receipt.locator(".money").last().innerText().catch(() => "");
  const shown = wonToNum(totalText.split("\n")[0]);
  const left = wonToNum(leftText.split("\n")[0]);
  const ok = sum === course.totals.price && shown === course.totals.price && (budget === undefined || left === Math.abs(budget - course.totals.price));
  report.money.push({ flow, id, sum, apiTotal: course.totals.price, receiptTotal: shown, budget, receiptLeft: left, apiLeft: course.totals.budget_left });
  note(flow, ok, `금액: 장소 합 ${sum} · API 합계 ${course.totals.price} · 영수증 합계 ${shown} · 남은 돈 ${left} (API ${course.totals.budget_left})`);
  const estimated = course.stops.filter((s) => s.place.price_is_estimated).length;
  const unknown = course.stops.filter((s) => s.est_price === 0 && !s.place.is_free && s.place.price_per_person !== 0).length;
  return { estimated, unknown, stops: course.stops.length };
}

const browser = await chromium.launch({ channel: "chrome" });

// ── FLOW A: Landing → Plan → Course (1440 · 390 · 430) ─────────────────────────
for (const vp of ["1440", "390", "430"]) {
  const flow = `A@${vp}`;
  const ctx = await context(browser, vp);
  const page = await ctx.newPage();
  watch(page, flow);
  try {
    const id = await wizard(page, flow);
    report.flows.push({ flow, id });
    if (vp === "1440") creatorState = await ctx.storageState();
    note(flow, (await overflowOf(page)) <= 1, `결과 화면 가로 넘침 ${await overflowOf(page)}px`);
    const m = await moneyCheck(page, flow, id);
    note(flow, true, `장소 ${m.stops}곳 중 평균가 ${m.estimated}곳 · 가격 모름 ${m.unknown}곳`);
    const receiptSays = await page.locator("[aria-label='예산 사용 현황']").innerText();
    note(flow, m.estimated === 0 || /예상|평균가/.test(receiptSays), "평균가가 섞인 합계를 확정값처럼 보이지 않는다");
    // 뒤로 가기: 고른 값이 남아 있나
    await page.goBack();
    await page.waitForURL(/\/plan/, { timeout: 15_000 }).catch(() => undefined);
    await page.waitForTimeout(1200);
    const onPlan = page.url().includes("/plan");
    const keeps = onPlan ? /홍대입구/.test(await page.locator("body").innerText()) : false;
    note(flow, !onPlan || keeps, `결과에서 뒤로 가면 위저드에 고른 값이 남아 있다 (${onPlan ? (keeps ? "남음" : "사라짐") : "위저드가 아님"})`);
    await page.screenshot({ path: path.join(OUT, `A-${vp}.png`) });
  } catch (e) {
    note(flow, false, `여정이 멈춤: ${String(e).slice(0, 200)}`);
    await page.screenshot({ path: path.join(OUT, `A-${vp}-stuck.png`) }).catch(() => undefined);
  }
  await ctx.close();
}

const courseId = report.flows.find((f) => f.id)?.id;

// ── FLOW B: Course → map → place → route → swap → budget → save ───────────────
if (courseId) {
  const flow = "B@1440";
  const ctx = await context(browser, "1440", true);
  const page = await ctx.newPage();
  watch(page, flow);
  try {
    await page.goto(`${WEB}/course/${courseId}`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[aria-label='코스 일정'] article");
    await page.waitForTimeout(2000);
    const pins = await page.locator(".jj-pin").count();
    note(flow, pins >= 2, `지도 핀 ${pins}개`);
    await page.locator(".jj-pin-drop", { hasText: /^2$/ }).first().click({ force: true });
    await page.waitForTimeout(1500);
    const active = await page.evaluate(() => document.querySelector("article[data-position='2']")?.className.includes("ring-2"));
    note(flow, Boolean(active), "핀 → 카드 강조");
    const legs = await page.locator("[aria-label='코스 일정'] > li[aria-label]").allInnerTexts();
    note(flow, legs.length >= 1 && legs.every((t) => /분|불러오지 못했/.test(t)), `이동 구간 ${legs.length}개가 시간/상태를 말한다`);
    // 바꾸기 → 더 저렴하게
    const card = page.locator("article[data-position='2']");
    await card.getByRole("button", { name: /바꾸기/ }).click();
    const cheaper = page.getByRole("button", { name: /^더 저렴하게$/ });
    await cheaper.click();
    const result = page.getByText(/바꿨어요|바꿀 만한 곳을 찾지 못했어요/).first();
    const told = await result.waitFor({ timeout: 20_000 }).then(() => true).catch(() => false);
    note(flow, told, `장소 바꾸기 결과를 알려 준다 (${told ? (await result.innerText()).slice(0, 40) : "알림 없음"})`);
    await moneyCheck(page, flow, courseId);
    // 저장 (익명) → 로그인으로
    await page.getByRole("button", { name: /코스 저장하기/ }).click();
    await page.waitForURL(/\/login/, { timeout: 15_000 }).catch(() => undefined);
    const login = page.url().includes("/login");
    note(flow, login, "익명으로 저장을 누르면 로그인으로 간다");
    if (login) {
      const enabled = await page.locator("a[href*='/auth/']").count();
      note(flow, enabled > 0, `로그인 수단 ${enabled}개가 켜져 있다 (0 이면 이 환경에서는 저장할 수 없다 — OAuth 키 필요)`);
    }
  } catch (e) {
    note(flow, false, `여정이 멈춤: ${String(e).slice(0, 200)}`);
    await page.screenshot({ path: path.join(OUT, "B-stuck.png") }).catch(() => undefined);
  }
  await ctx.close();
}

// ── FLOW C: Course → share → another visitor → restore; refresh ───────────────
if (courseId) {
  const flow = "C@1440";
  const ctx = await context(browser, "1440", true);
  const page = await ctx.newPage();
  watch(page, flow);
  try {
    await page.goto(`${WEB}/course/${courseId}`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[aria-label='코스 일정'] article");
    await page.evaluate(() => {
      // 데스크톱 크롬의 navigator.share 가 있으면 공유 시트를 띄우므로 복사 경로를 쓰게 한다
      Object.defineProperty(navigator, "share", { value: undefined, configurable: true });
    });
    await page.getByRole("button", { name: "코스 공유하기" }).first().click();
    await page.waitForTimeout(600);
    const copied = await page.evaluate(() => navigator.clipboard.readText()).catch(() => "");
    note(flow, copied.includes(`/course/${courseId}`), `공유: 링크가 복사된다 (${copied.slice(-40)})`);
    const other = await context(browser, "390");
    const p2 = await other.newPage();
    watch(p2, flow);
    await p2.goto(copied || `${WEB}/course/${courseId}`, { waitUntil: "domcontentloaded" });
    await p2.waitForSelector("[aria-label='코스 일정'] article", { timeout: 30_000 });
    await p2.waitForTimeout(1500);
    note(flow, await p2.getByText(/친구가 짠 코스예요/).isVisible(), "다른 사람이 열면 같은 코스 + '친구가 짠 코스'");
    note(flow, await p2.getByRole("button", { name: /이 코스로 내 코스 만들기/ }).isVisible(), "받은 사람의 다음 행동이 보인다");
    await other.close();
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector("[aria-label='코스 일정'] article", { timeout: 30_000 });
    note(flow, true, "새로고침해도 결과가 복원된다");
  } catch (e) {
    note(flow, false, `여정이 멈춤: ${String(e).slice(0, 200)}`);
  }
  await ctx.close();
}

// ── FLOW D: Mobile → course → sheet → map → external map ─────────────────────
if (courseId) {
  for (const vp of ["390", "430"]) {
    const flow = `D@${vp}`;
    const ctx = await context(browser, vp, true);
    const page = await ctx.newPage();
    watch(page, flow);
    try {
      await page.goto(`${WEB}/course/${courseId}`, { waitUntil: "domcontentloaded" });
      await page.waitForSelector("[aria-label='코스 일정'] article");
      await page.waitForTimeout(1500);
      await page.getByRole("button", { name: "지도 크게", exact: true }).click();
      await page.waitForTimeout(600);
      await page.getByRole("button", { name: "지도 닫기", exact: true }).click();
      await page.getByRole("button", { name: "목록 크게 보기" }).click();
      await page.waitForTimeout(600);
      const mapH = await page.evaluate(() => Math.round(document.querySelector(".jj-map")?.getBoundingClientRect().height ?? -1));
      note(flow, mapH === 0, `시트 세 단계 (목록 전체에서 지도 ${mapH}px)`);
      await page.getByRole("button", { name: "목록 접기" }).click();
      const href = await page.getByRole("link", { name: /네이버 지도에서 길찾기/ }).getAttribute("href");
      note(flow, /^https:\/\/map\.naver\.com\/p\/directions\//.test(href ?? ""), "외부 지도(네이버) 링크");
      const save = await page.getByRole("button", { name: /코스 저장하기/ }).boundingBox();
      note(flow, Boolean(save && save.height >= 44), `하단 저장 버튼 높이 ${save?.height}px`);
      note(flow, (await overflowOf(page)) <= 1, `가로 넘침 ${await overflowOf(page)}px`);
      await page.screenshot({ path: path.join(OUT, `D-${vp}.png`) });
    } catch (e) {
      note(flow, false, `여정이 멈춤: ${String(e).slice(0, 200)}`);
    }
    await ctx.close();
  }
}

// ── 화면별 가로 넘침 · 콘솔 (여섯 폭) ────────────────────────────────────────
const PAGES = ["/", "/home", "/plan", courseId ? `/course/${courseId}` : null, "/explore", "/my", "/login", "/chat", "/nowhere"].filter(Boolean);
for (const vp of Object.keys(VIEWPORTS)) {
  const ctx = await context(browser, vp);
  const page = await ctx.newPage();
  watch(page, `pages@${vp}`);
  for (const p of PAGES) {
    await page.goto(`${WEB}${p}`, { waitUntil: "domcontentloaded" }).catch(() => undefined);
    await page.waitForTimeout(p.startsWith("/course") ? 3500 : 1800);
    const o = await overflowOf(page);
    if (o > 1) report.overflow.push({ vp, page: p, px: o });
  }
  await ctx.close();
}
note("pages", report.overflow.length === 0, `여섯 폭 × ${PAGES.length}화면 가로 넘침 ${report.overflow.length}건 ${JSON.stringify(report.overflow)}`);

await browser.close();
const errors = report.console.filter((c) => c.type !== "warning");
console.log(`\n콘솔 오류 ${errors.length} · 경고 ${report.console.length - errors.length} · 실패한 요청 ${report.network.length} · 문제 ${report.findings.length}`);
const group = (rows, key) => Object.entries(rows.reduce((m, r) => ((m[key(r)] = (m[key(r)] ?? 0) + 1), m), {}));
for (const [k, n] of group(report.console, (c) => `${c.type}: ${c.text.slice(0, 120)}`)) console.log(`  ${n}× ${k}`);
for (const [k, n] of group(report.network, (r) => `${r.status} ${r.url.split("?")[0]}`)) console.log(`  ${n}× ${k}`);
writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
process.exit(report.findings.length ? 1 : 0);
