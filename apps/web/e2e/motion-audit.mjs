// 모션 점검 (docs/32): 랜딩의 첫 방문 시퀀스(오늘의 경로 → 예산이 세어짐 → 영수증 출력 → 짠이 → 행동)를 시간대별로 찍고,
// 끝난 뒤에는 모든 장면이 온전히 보이는지(투명 · 잘림이 남지 않았는지), 예산이 끝까지 세어졌는지 확인한다.
// 모션을 줄인 환경(prefers-reduced-motion)에서는 처음부터 다 보여야 한다. 자동화 브라우저는 시퀀스를 건너뛰므로
// (검증 · 캡처가 중간 프레임을 찍지 않게) 여기서는 navigator.webdriver 를 숨겨 실제 방문자처럼 연다.
//   node e2e/motion-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const outDir = process.argv[2] ?? "motion-audit";
mkdirSync(outDir, { recursive: true });
const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

/** 히어로에서 아직 덜 보이는 장면의 수: [data-beat] · 경로의 점과 선 중 opacity < 1 이거나 clip 이 남은 것 */
const unfinished = (page) =>
  page.evaluate(() => {
    const els = [...document.querySelectorAll(".hero-intro [data-beat], .hero-intro .route-dot, .hero-intro .route-seg, .hero-intro .route-text")];
    const open = (clip) => clip === "none" || (clip.match(/-?[\d.]+/g) ?? []).every((n) => Number(n) === 0);
    return els.filter((el) => {
      // 그 폭에서 그려지지 않는 것(display:none — 좁은 화면 전용 장면 등)은 셀 대상이 아니다
      if (el.getClientRects().length === 0) return false;
      const s = getComputedStyle(el);
      return Number(s.opacity) < 0.99 || !open(s.clipPath);
    }).length;
  });
const budgetText = (page) => page.locator(".hero-intro [data-beat='money'] [aria-hidden]").first().textContent();

const browser = await chromium.launch({ channel: "chrome" });
for (const reduced of [false, true]) {
  const tag = reduced ? "reduced" : "motion";
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR", reducedMotion: reduced ? "reduce" : "no-preference" });
  await context.addInitScript(() => Object.defineProperty(navigator, "webdriver", { get: () => false }));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  // 첫 페인트부터 잰다: 시간표는 CSS 라 스크립트(개발 서버에서는 몇 초 늦다)를 기다리지 않는다
  await page.goto(WEB, { timeout: 120000, waitUntil: "commit" });
  await page.locator(".hero-intro").first().waitFor({ state: "attached", timeout: 60000 });
  // 개발 서버는 스타일을 스크립트로 넣는다 → 스타일이 붙기 전에 재면 아무것도 움직이지 않는 것처럼 보인다. 붙은 뒤에 첫 값을 잰다
  await page.waitForFunction(() => { const el = document.querySelector(".hero-intro"); return el && getComputedStyle(el).position === "relative"; }, null, { timeout: 60000, polling: 16 });
  // 스타일이 붙은 첫 프레임에는 애니메이션이 아직 만들어지지 않았다(0개) → 모션 환경에서는 히어로의 애니메이션이 생긴 뒤에 잰다
  if (!reduced) await page.waitForFunction(() => document.getAnimations().some((a) => a.effect?.target?.closest?.(".hero-intro")), null, { timeout: 5000, polling: 16 }).catch(() => undefined);
  const playing = await page.evaluate(() => document.documentElement.getAttribute("data-intro") === "play");
  const early = await unfinished(page);
  const frames = [];
  for (const at of [300, 900, 1400, 1900, 2400]) {
    await page.waitForTimeout(at - (frames.at(-1) ?? 0));
    frames.push(at);
    await page.screenshot({ path: path.join(outDir, `${tag}-${String(at).padStart(4, "0")}ms.png`) });
  }
  await page.waitForTimeout(900);
  const late = await unfinished(page);
  await page.screenshot({ path: path.join(outDir, `${tag}-settled.png`) });
  console.log(`${tag}: 시퀀스 ${playing ? "재생" : "건너뜀"} · 처음 ${early}개가 아직 놓이는 중 → 끝난 뒤 ${late}개`);
  if (reduced) {
    check(!playing, "reduced: 모션을 줄인 환경에서는 시퀀스를 틀지 않는다");
    check(early === 0, "reduced: 처음부터 다 보인다");
  } else {
    check(playing, "motion: 첫 방문이면 시퀀스를 튼다");
    check(early > 0, "motion: 처음에는 장면이 차례를 기다린다");
  }
  check(late === 0, `${tag}: 3.3초 뒤에는 모든 장면이 온전히 보인다`);
  check((await budgetText(page))?.includes("50,000"), `${tag}: 예산이 끝까지 세어져 50,000원이다`);
  check(errors.length === 0, `${tag}: 페이지 에러 0건${errors.length ? ` — ${errors[0]}` : ""}`);
  // 같은 세션에서 다시 오면 틀지 않는다
  if (!reduced) {
    await page.goto(WEB, { timeout: 120000, waitUntil: "domcontentloaded" });
    await page.locator(".hero-intro").first().waitFor();
    check((await page.evaluate(() => document.documentElement.getAttribute("data-intro"))) !== "play", "motion: 같은 세션의 두 번째 방문은 시퀀스 없이 바로");
  }
  await context.close();
}
// 지도 핀: 코스가 처음 그려질 때 순번대로 내려앉고, 끝난 뒤에는 모두 제자리에 온전히 보인다. 핀을 고르거나 줌을 바꿔도 다시 재생하지 않는다.
{
  const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
  const d = new Date();
  d.setDate(d.getDate() + 3);
  const made = await (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 70000, start_at: `${d.toISOString().slice(0, 10)}T18:00:00+09:00`, alternatives: 0 }) })).json();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.__pins = [];
    const timer = setInterval(() => {
      const drops = [...document.querySelectorAll(".jj-pin .jj-pin-drop")];
      if (drops.length === 0) return;
      // 제자리까지 남은 거리(px): translate 의 y 값과 --dy 의 차이. 0 이면 내려앉았다
      window.__pins.push(drops.map((el) => { const y = Number((getComputedStyle(el).translate.split(" ")[1] ?? "0").replace("px", "")); const dy = Number(getComputedStyle(el).getPropertyValue("--dy").replace("px", "") || 0); return Math.abs(y - dy).toFixed(0); }).join(","));
      if (window.__pins.length > 40) clearInterval(timer);
    }, 60);
  });
  await page.goto(`${WEB}/course/${made.courses[0].id}`, { timeout: 120000 });
  await page.locator(".jj-pin-drop").first().waitFor({ timeout: 60000 }); // .jj-pin 은 0×0 기준점이라 "보인다"로 잡히지 않는다
  await page.waitForTimeout(3200);
  const seen = await page.evaluate(() => window.__pins);
  // 핀은 opacity 가 아니라 위치(translate)로 내려앉는다 (globals.css pin-land: 투명에서 시작하면 핀 없는 지도가 보였다) → 앞 번호가 먼저 제자리에 오는지 본다
  const staggered = seen.some((row) => { const v = row.split(",").map(Number); return v[0] < v[v.length - 1]; });
  console.log("핀:", [...new Set(seen)].slice(0, 8).join(" → "));
  check(staggered, "핀이 순번대로 내려앉는다 (앞 번호가 먼저 보인다)");
  check(seen[seen.length - 1].split(",").every((v) => Number(v) === 0), "끝난 뒤 모든 핀이 제자리에 있다");
  // 이미 골라진 핀을 누르면 다시 그릴 일이 없어 검사가 되지 않는다 → 골라지지 않은 핀을 누른다
  // (첫 장소 카드가 스크롤 띠에 들어와 있으면 1번 핀은 처음부터 골라져 있다)
  await page.locator(".jj-pin:not(.is-active) .jj-pin-drop").first().click();
  await page.waitForTimeout(400);
  const replay = await page.evaluate(() => [...document.querySelectorAll(".jj-pin")].filter((el) => el.classList.contains("is-landing")).length);
  check(replay === 0, "핀을 골라도 내려앉는 연출이 다시 재생되지 않는다");
  await page.screenshot({ path: path.join(outDir, "pins-settled.png") });
  await context.close();
}

await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
