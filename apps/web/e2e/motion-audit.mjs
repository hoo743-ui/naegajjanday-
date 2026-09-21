// 모션 점검: 영수증이 "출력"되는 동안과 끝난 뒤를 찍고, 끝난 뒤에는 모든 줄이 온전히 보이는지 확인한다.
// 모션을 줄인 환경(prefers-reduced-motion)에서는 처음부터 다 보여야 한다.
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

/** 영수증 안에서 아직 덜 보이는 줄의 수 (opacity < 1 이거나 clip 이 남아 있는 것) */
const unfinished = (page) =>
  page.evaluate(() => {
    const receipt = document.querySelector(".receipt");
    if (!receipt) return -1;
    const clipped = getComputedStyle(receipt).clipPath;
    const dim = [...receipt.querySelectorAll(".receipt-line")].filter((el) => Number(getComputedStyle(el).opacity) < 0.99).length;
    // 끝난 상태는 브라우저마다 "inset(0px)" · "inset(0px 0px 0%)" 처럼 적힌다 → 숫자가 모두 0 인지로 본다
    const open = clipped === "none" || (clipped.match(/-?[\d.]+/g) ?? []).every((n) => Number(n) === 0);
    return dim + (open ? 0 : 1);
  });

const browser = await chromium.launch({ channel: "chrome" });
for (const reduced of [false, true]) {
  const tag = reduced ? "reduced" : "motion";
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR", reducedMotion: reduced ? "reduce" : "no-preference" });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
  await page.goto(WEB, { timeout: 120000, waitUntil: "domcontentloaded" });
  await page.locator(".receipt").first().waitFor({ timeout: 60000 });
  const early = await unfinished(page);
  await page.screenshot({ path: path.join(outDir, `${tag}-0-early.png`) });
  await page.waitForTimeout(2600);
  const late = await unfinished(page);
  await page.screenshot({ path: path.join(outDir, `${tag}-1-settled.png`) });
  console.log(`${tag}: 처음 ${early}줄이 찍히는 중 → 끝난 뒤 ${late}줄`);
  check(late === 0, `${tag}: 끝난 뒤 영수증의 모든 줄이 온전히 보인다`);
  if (reduced) check(early === 0, "reduced: 모션을 줄인 환경에서는 처음부터 다 보인다");
  check(errors.length === 0, `${tag}: 페이지 에러 0건`);
  await context.close();
}
await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
