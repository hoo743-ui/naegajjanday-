// 화면 점검용 캡처: 모든 라우트를 데스크톱·모바일에서 "사용자가 스크롤하며 보는 그대로" 구간별로 찍는다.
//   node e2e/visual-audit.mjs [outDir] [--only=landing,plan]
// E2E(통과/실패)와 달리 사람이(또는 Claude 가) 눈으로 보고 디자인·렌더링 결함을 찾기 위한 것.
import { chromium, devices } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "visual-audit";
const only = (process.argv.find((a) => a.startsWith("--only=")) ?? "").replace("--only=", "").split(",").filter(Boolean);
mkdirSync(outDir, { recursive: true });

const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  mobile: { ...devices["Pixel 7"] },
};

async function makeCourse(style = "efficient") {
  const d = new Date();
  d.setDate(d.getDate() + 3);
  const res = await fetch(`${API}/courses/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 70000, style,
      start_at: `${d.toISOString().slice(0, 10)}T18:00:00+09:00`, duration_min: 240,
    }),
  });
  return (await res.json()).courses[0].id;
}

const log = [];
/** 위에서부터 한 화면씩 내려가며 찍는다 — 고정(sticky)·스크롤 연동 구간이 실제로 어떻게 보이는지 드러난다. */
async function shootScrolling(page, name, maxShots = 12) {
  const step = Math.round(page.viewportSize().height * 0.9);
  for (let i = 0; i < maxShots; i++) {
    await page.waitForTimeout(650);
    await page.screenshot({ path: path.join(outDir, `${name}-${String(i).padStart(2, "0")}.png`) });
    // 사이트가 scroll-behavior: smooth 라 scrollBy 직후에는 위치가 아직 안 바뀐다 → 즉시 이동으로 잰다
    const moved = await page.evaluate((dy) => {
      const before = window.scrollY;
      window.scrollTo({ top: before + dy, behavior: "instant" });
      return window.scrollY - before;
    }, step);
    if (moved < 8) break;
  }
}

const SCENES = {
  landing: async (page, tag) => { await page.goto(`${WEB}/home`); await page.waitForTimeout(1500); await shootScrolling(page, `${tag}-landing`, 10); },
  plan: async (page, tag) => {
    await page.goto(`${WEB}/plan`);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(outDir, `${tag}-plan-1-region.png`) });
    await page.goto(`${WEB}/plan?region=seoul-hongdae&purpose=date`);
    await page.waitForTimeout(1500);
    for (const [i, label] of [[2, "purpose"], [3, "budget"], [4, "taste"]]) {
      await page.getByRole("button", { name: "다음", exact: true }).click();
      await page.waitForTimeout(900);
      await shootScrolling(page, `${tag}-plan-${i}-${label}`, 3);
      await page.evaluate(() => window.scrollTo(0, 0));
    }
  },
  course: async (page, tag) => { await page.goto(`${WEB}/course/${await makeCourse()}`); await page.waitForTimeout(4000); await shootScrolling(page, `${tag}-course`, 6); },
  explore: async (page, tag) => { await page.goto(`${WEB}/explore`); await page.waitForTimeout(3500); await shootScrolling(page, `${tag}-explore`, 4); },
  chat: async (page, tag) => { await page.goto(`${WEB}/chat`); await page.waitForTimeout(2000); await page.screenshot({ path: path.join(outDir, `${tag}-chat.png`) }); },
  my: async (page, tag) => { await page.goto(`${WEB}/my`); await page.waitForTimeout(2000); await page.screenshot({ path: path.join(outDir, `${tag}-my.png`) }); },
  login: async (page, tag) => { await page.goto(`${WEB}/login`); await page.waitForTimeout(1500); await page.screenshot({ path: path.join(outDir, `${tag}-login.png`) }); },
  notfound: async (page, tag) => { await page.goto(`${WEB}/no-such-page`); await page.waitForTimeout(1500); await page.screenshot({ path: path.join(outDir, `${tag}-404.png`) }); },
};

const browser = await chromium.launch({ channel: "chrome" });
for (const [tag, opts] of Object.entries(VIEWPORTS)) {
  const context = await browser.newContext({ ...opts, locale: "ko-KR" });
  const page = await context.newPage();
  page.on("console", (m) => m.type() === "error" && log.push(`[${tag}] console: ${m.text().slice(0, 200)}`));
  page.on("pageerror", (e) => log.push(`[${tag}] pageerror: ${String(e).slice(0, 200)}`));
  page.on("response", (r) => r.status() >= 400 && !r.url().includes("/auth/refresh") && log.push(`[${tag}] ${r.status()} ${r.url().slice(0, 140)}`));
  for (const [name, scene] of Object.entries(SCENES)) {
    if (only.length && !only.includes(name)) continue;
    try {
      await scene(page, tag);
    } catch (e) {
      log.push(`[${tag}] ${name} FAILED: ${String(e).slice(0, 300)}`);
    }
  }
  await context.close();
}
await browser.close();
writeFileSync(path.join(outDir, "log.txt"), log.join("\n") || "(no console errors, page errors or failed responses)");
console.log(`saved to ${outDir}\n${log.join("\n") || "clean"}`);
