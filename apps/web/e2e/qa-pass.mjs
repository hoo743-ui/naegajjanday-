// 디자인 QA 2차 (docs/32 C): 실제 사용자 흐름을 네 가지 폭(1440 · 1280 · 430 · 390)에서 그대로 밟으며 화면을 찍고,
// 눈으로 보기 전에 기계가 먼저 잡을 수 있는 것을 센다 — 가로 넘침 · 잘린 글자 · 작은 터치 영역 · 깨진 사진 · 콘솔/페이지 에러 · 실패한 요청.
// 흐름: 랜딩 → 위저드 4단계 → 로딩 → 결과(첫 화면 · 일정 · 영수증) → 장소 상세 → 장소 바꾸기 → 저장(로그인으로) → 공유 → 내 코스 → 없는 코스(오류) → 404.
//   node e2e/qa-pass.mjs [outDir] [--only=1440,390]
// 결과: outDir/*.png 와 outDir/report.md (화면별 자동 점검 표). 자동화 브라우저라 랜딩 시퀀스는 건너뛴다(모션은 motion-audit.mjs).
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const outDir = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "qa-pass";
const only = (process.argv.find((a) => a.startsWith("--only=")) ?? "").replace("--only=", "").split(",").filter(Boolean);
mkdirSync(outDir, { recursive: true });

const WIDTHS = [
  { tag: "1440", viewport: { width: 1440, height: 900 }, mobile: false },
  { tag: "1280", viewport: { width: 1280, height: 800 }, mobile: false },
  { tag: "430", viewport: { width: 430, height: 932 }, mobile: true },
  { tag: "390", viewport: { width: 390, height: 844 }, mobile: true },
].filter((w) => !only.length || only.includes(w.tag));

/** 화면 하나의 기계 점검. 눈으로 볼 것을 대신하지 않는다 — 놓치기 쉬운 것만 센다 */
async function audit(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      // 화면 낭독기 전용(sr-only: 1×1 · clip · clip-path inset(50%))은 눈에 보이는 것이 아니다 — 기울인 영수증 안에서는 1×1 이 1.03px 로 재진다
      return r.width > 1 && r.height > 1 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05 && s.clip !== "rect(0px, 0px, 0px, 0px)" && s.clipPath !== "inset(50%)";
    };
    // 지도 SDK 가 그리는 것(로고 · 확대 버튼)은 우리가 고칠 수 없다 → 세지 않는다
    const ours = (el) => !el.closest(".jj-map, .leaflet-container");
    const name = (el) => (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
    const overflowX = document.documentElement.scrollWidth - window.innerWidth;
    // 잘린 글자: 넘치는데 말줄임(…)도 스크롤도 아닌 곳 — 글자가 그냥 잘려 나간다
    const clipped = [...document.querySelectorAll("body *")]
      .filter((el) => el.childElementCount === 0 && (el.textContent ?? "").trim().length > 1 && visible(el) && ours(el))
      .filter((el) => {
        const s = getComputedStyle(el);
        const hides = s.overflowX === "hidden" || s.overflowX === "clip";
        return hides && s.textOverflow !== "ellipsis" && el.scrollWidth > el.clientWidth + 2 && !s.webkitLineClamp?.match?.(/\d/);
      })
      .map(name);
    // 터치 영역: 44px(브리프 기준) · 24px(WCAG 2.2 AA 최소). 문장 속 글자 링크는 빼고 센다
    const targets = [...document.querySelectorAll("button, a[href], [role='button'], [role='tab'], [role='radio'], [role='checkbox'], input:not([type='hidden']), summary")]
      // 문장 속 글자 링크 · 바닥글 · 슬라이더(손잡이가 28px)는 빼고 센다
      .filter((el) => visible(el) && ours(el) && !el.closest("p, li > p, footer") && el.getAttribute("type") !== "range")
      .map((el) => ({ el, r: el.getBoundingClientRect() }));
    const under44 = targets.filter(({ r }) => Math.min(r.width, r.height) < 44).map(({ el, r }) => `${name(el) || el.tagName} ${Math.round(r.width)}×${Math.round(r.height)}`);
    const under24 = targets.filter(({ r }) => Math.min(r.width, r.height) < 24).map(({ el, r }) => `${name(el) || el.tagName} ${Math.round(r.width)}×${Math.round(r.height)}`);
    const brokenImages = [...document.images].filter((img) => img.complete && img.naturalWidth === 0 && visible(img)).map((img) => img.src.slice(0, 80));
    return { overflowX, clipped: [...new Set(clipped)], under44: [...new Set(under44)], under24: [...new Set(under24)], brokenImages };
  });
}

const rows = [];
const browser = await chromium.launch({ channel: "chrome" });
for (const w of WIDTHS) {
  const context = await browser.newContext({ viewport: w.viewport, deviceScaleFactor: w.mobile ? 2 : 1, isMobile: w.mobile, hasTouch: w.mobile, locale: "ko-KR", permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  let events = [];
  page.on("console", (m) => m.type() === "error" && events.push(`console: ${m.text().slice(0, 160)}`));
  page.on("pageerror", (e) => events.push(`pageerror: ${String(e).slice(0, 160)}`));
  page.on("response", (r) => r.status() >= 400 && !r.url().includes("/auth/refresh") && !r.url().includes("no-such") && !r.url().includes("00000000-0000") && events.push(`${r.status()} ${r.url().slice(0, 120)}`));

  const shot = async (scene, { full = false } = {}) => {
    await page.waitForTimeout(700);
    const file = `${w.tag}-${scene}.png`;
    await page.screenshot({ path: path.join(outDir, file), fullPage: full });
    const a = await audit(page);
    rows.push({ width: w.tag, scene, file, ...a, events });
    events = [];
    console.log(`[${w.tag}] ${scene}: 넘침 ${a.overflowX}px · 잘림 ${a.clipped.length} · 44px 미만 ${a.under44.length} (24px 미만 ${a.under24.length}) · 깨진 사진 ${a.brokenImages.length}`);
  };
  const step = async (label, fn) => {
    try {
      await fn();
    } catch (e) {
      rows.push({ width: w.tag, scene: label, file: "", overflowX: 0, clipped: [], under44: [], under24: [], brokenImages: [], events: [...events, `FAILED: ${String(e).slice(0, 200)}`] });
      events = [];
      console.log(`[${w.tag}] ${label} FAILED: ${String(e).slice(0, 200)}`);
    }
  };

  await step("landing", async () => {
    await page.goto(`${WEB}/`, { timeout: 120000 });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 60000 });
    await shot("01-landing");
    await page.locator("#purposes").scrollIntoViewIfNeeded();
    await shot("02-landing-purposes");
  });

  let courseUrl = "";
  await step("plan", async () => {
    await page.goto(`${WEB}/plan?region=seoul-hongdae&purpose=date`, { timeout: 120000 });
    await page.getByRole("heading", { level: 1 }).waitFor({ timeout: 60000 });
    await shot("03-plan-region");
    for (const [n, label] of [[4, "purpose"], [5, "budget"], [6, "taste"]]) {
      await page.getByRole("button", { name: "다음", exact: true }).click();
      await page.waitForTimeout(600);
      await shot(`0${n}-plan-${label}`);
    }
    await page.getByRole("checkbox", { name: /특별한 경험/ }).click();
    await page.getByText("좋아요. 이렇게 이해했어요.").scrollIntoViewIfNeeded();
    await shot("07-plan-understood");
    await page.getByRole("button", { name: /코스 짜 주세요/ }).click();
    await page.waitForTimeout(500);
    await shot("08-loading");
    await page.waitForURL(/\/course\/[0-9a-f-]{36}/, { timeout: 120000 });
    courseUrl = page.url();
  });

  await step("result", async () => {
    if (!courseUrl) throw new Error("코스가 만들어지지 않아 결과 화면을 건너뜀");
    await page.getByLabel("코스 일정").waitFor({ timeout: 60000 });
    await page.waitForTimeout(1500);
    await shot("09-result-first");
    await page.getByLabel("코스 일정").scrollIntoViewIfNeeded();
    await shot("10-result-dayflow");
    await page.getByRole("heading", { name: "오늘의 영수증" }).scrollIntoViewIfNeeded();
    await shot("11-result-receipt");
  });

  await step("place", async () => {
    if (!courseUrl) return;
    await page.goto(courseUrl, { timeout: 120000 });
    await page.getByLabel("코스 일정").waitFor({ timeout: 60000 });
    await page.locator("article h3 button").first().click();
    await page.getByRole("dialog").waitFor({ timeout: 20000 });
    await shot("12-place-detail");
    await page.keyboard.press("Escape");
  });

  await step("swap", async () => {
    if (!courseUrl) return;
    const before = await page.locator("[aria-label='오늘의 요약']").innerText();
    // 바꾸기 시트 → 짠이에게 맡기기 · 더 저렴하게 (docs/42)
    await page.getByRole("button", { name: /다른 곳으로 바꾸기/ }).first().click();
    await page.getByRole("button", { name: /^더 저렴하게$/ }).click();
    await page.waitForFunction((b) => document.querySelector("[aria-label='오늘의 요약']")?.textContent !== b || document.body.textContent?.includes("찾지 못했어요"), before.slice(0, 200), { timeout: 30000 }).catch(() => {});
    // 바뀐 장소 줄은 제자리로 미끄러져 들어간다(layout 애니메이션) → 다 끝난 뒤에 찍는다
    await page.waitForTimeout(2500);
    await shot("13-after-swap");
  });

  await step("share-save", async () => {
    if (!courseUrl) return;
    const share = w.mobile ? page.getByRole("button", { name: "코스 공유하기" }).last() : page.getByRole("banner").getByRole("button", { name: "코스 공유하기" });
    await share.click().catch(() => {});
    await shot("14-share");
    await page.getByRole("button", { name: /코스 저장하기/ }).click();
    await page.waitForURL(/\/login/, { timeout: 20000 });
    await shot("15-save-login");
  });

  await step("my", async () => {
    await page.goto(`${WEB}/my`, { timeout: 120000 });
    await page.waitForTimeout(1500);
    await shot("16-my");
  });

  await step("error", async () => {
    await page.goto(`${WEB}/course/00000000-0000-4000-8000-000000000000`, { timeout: 120000 });
    await page.waitForTimeout(2500);
    await shot("17-course-missing");
    await page.goto(`${WEB}/no-such-page`, { timeout: 120000 });
    await page.waitForTimeout(1200);
    await shot("18-404");
  });

  await context.close();
}
await browser.close();

const list = (xs, n = 6) => (xs.length ? `${xs.length} — ${xs.slice(0, n).join(" / ")}${xs.length > n ? " …" : ""}` : "0");
const md = [
  "# 디자인 QA 2차 — 자동 점검 (e2e/qa-pass.mjs)",
  "",
  `실행 ${new Date().toISOString()} · ${WEB}`,
  "",
  "| 폭 | 화면 | 가로 넘침 | 잘린 글자 | 44px 미만 | 24px 미만 | 깨진 사진 | 에러 · 실패 요청 |",
  "|---|---|---|---|---|---|---|---|",
  ...rows.map((r) => `| ${r.width} | ${r.file ? `[${r.scene}](${r.file})` : r.scene} | ${r.overflowX > 1 ? `**${r.overflowX}px**` : "0"} | ${list(r.clipped, 3)} | ${list(r.under44, 4)} | ${list(r.under24, 4)} | ${list(r.brokenImages, 2)} | ${r.events.length ? r.events.slice(0, 3).join("<br>") : "0"} |`),
];
writeFileSync(path.join(outDir, "report.md"), md.join("\n"));
const bad = rows.filter((r) => r.overflowX > 1 || r.under24.length || r.brokenImages.length || r.events.length);
console.log(`\n${rows.length}개 화면 · 확인이 필요한 화면 ${bad.length}개 → ${path.join(outDir, "report.md")}`);
