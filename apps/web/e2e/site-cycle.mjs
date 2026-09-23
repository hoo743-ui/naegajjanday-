// 전체 사이클 검증: 모든 화면 × 3개 뷰포트를 실제 API 로 돌며 "오류가 하나도 없는가"와 "있어야 할 것이 다 있는가"를 본다.
//
//   node e2e/site-cycle.mjs                  검증 (문제가 하나라도 있으면 종료 코드 1)
//   node e2e/site-cycle.mjs --record         지금 화면을 계약서(e2e/content-contract.json)로 기록
//   node e2e/site-cycle.mjs --record --intersect   한 번 더 돌려, 두 번 다 보인 것만 남긴다 (로딩 문구 · 그날의 데이터 제거)
//   node e2e/site-cycle.mjs --only=plan,course --shots=폴더
//
// 잡는 것:  페이지 에러 · 콘솔 에러 · 실패한 요청(4xx/5xx, 요청 실패) · 에러 화면 · 가로 넘침 · 깨진 이미지 ·
//           이름 없는 버튼/링크 · 계약서에 있던 문구(제목 · 버튼 · 링크 · 라벨)가 사라진 것
// 계약서는 "지금 보이는 것은 디자인을 바꿔도 다 나와야 한다"는 약속이다. 문구를 일부러 바꿨으면 --record 로 다시 기록한다.
import { chromium, devices } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { asCreator, remember } from "./creator.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const CONTRACT = path.join(HERE, "content-contract.json");
const args = process.argv.slice(2);
const record = args.includes("--record");
const intersect = args.includes("--intersect");
const only = (args.find((a) => a.startsWith("--only=")) ?? "").replace("--only=", "").split(",").filter(Boolean);
const shots = (args.find((a) => a.startsWith("--shots=")) ?? "").replace("--shots=", "");
if (shots) mkdirSync(shots, { recursive: true });

const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 } },
  tablet: { viewport: { width: 820, height: 1180 } },
  mobile: devices["Pixel 7"],
};

// 알려진 소음: 비로그인 세션 복원(401), 카카오 SDK 가 없는 파노라마 타일에 대해 스스로 남기는 로그
const IGNORE_CONSOLE = [/401 \(Unauthorized\)/, /image loading error/, /Download the React DevTools/, /\[Fast Refresh\]/];
const IGNORE_REQUEST = [/\/v1\/auth\/refresh/, /dapi\.kakao\.com|daumcdn\.net|kakaocdn/, /_next\/static\/webpack\/.*hot-update/];

const post = async (body) => {
  const res = await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`generate ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return remember(await res.json()); // 도구가 만든 코스를 만든 사람으로 연다 (docs/28)
};
const day = (() => {
  const d = new Date();
  d.setDate(d.getDate() + 3);
  return d.toISOString().slice(0, 10);
})();

/** 한 화면을 끝까지 내려가며 늦게 나타나는 구간(Reveal · lazy 이미지)까지 그리게 한다 */
async function scrollThrough(page) {
  const step = Math.round(page.viewportSize().height * 0.85);
  for (let i = 0; i < 14; i += 1) {
    const moved = await page.evaluate((dy) => {
      const before = window.scrollY;
      window.scrollTo({ top: before + dy, behavior: "instant" });
      return window.scrollY - before;
    }, step);
    await page.waitForTimeout(350);
    if (moved < 8) break;
  }
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
}

/** 화면에 보이는, 사람이 읽고 누르는 것들. 데이터(가게 이름 · 금액)가 아니라 **뼈대 문구**만 계약서에 남긴다. */
async function inventory(page, dynamicRoots) {
  return page.evaluate((roots) => {
    // 데이터 구역, 그리고 로딩 중에만 잠깐 보이는 것(스켈레톤 · aria-busy)은 계약이 아니다
    const skip = (el) => roots.some((sel) => el.closest(sel)) || el.closest(".skeleton-shimmer,[aria-busy='true']") !== null;
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
    };
    const clean = (t) => (t ?? "").replace(/\s+/g, " ").trim();
    const hasDigits = (t) => /\d/.test(t);
    const out = { headings: [], buttons: [], links: [], labels: [] };
    const push = (bucket, text) => {
      const t = clean(text);
      if (t && t.length <= 40 && !hasDigits(t) && !out[bucket].includes(t)) out[bucket].push(t);
    };
    document.querySelectorAll("h1,h2,h3,legend").forEach((el) => visible(el) && !skip(el) && push("headings", el.textContent));
    document.querySelectorAll("button,[role=button],[role=tab],[role=radio]").forEach((el) => visible(el) && !skip(el) && push("buttons", el.getAttribute("aria-label") || el.textContent));
    document.querySelectorAll("a[href]").forEach((el) => visible(el) && !skip(el) && push("links", el.getAttribute("aria-label") || el.textContent));
    document.querySelectorAll("label,[aria-label]").forEach((el) => visible(el) && !skip(el) && el.tagName !== "BUTTON" && el.tagName !== "A" && push("labels", el.getAttribute("aria-label") || el.textContent));
    const unnamed = [...document.querySelectorAll("button,a[href]")].filter((el) => visible(el) && !clean(el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent) && !el.querySelector("img[alt]:not([alt=''])")).length;
    const broken = [...document.images].filter((img) => visible(img) && img.complete && img.naturalWidth === 0).map((img) => img.currentSrc.slice(0, 120));
    return { ...out, unnamed, broken };
  }, dynamicRoots);
}

async function main() {
  // 실제 데이터로 만든 코스 세 가지: 보통 · 여러 동네 · 1박 2일
  const plain = (await post({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 80000, start_at: `${day}T18:00:00+09:00`, duration_min: 240 })).courses[0];
  const hop = (await post({ regions: ["seoul-hongdae", "seoul-seongsu"], purpose: "friends", purposes: ["date"], party_size: 3, budget_total: 150000, start_at: `${day}T12:00:00+09:00`, duration_min: 420, conditions: ["rain"] })).courses[0];
  const trip = (await post({ region: "gangneung-downtown", purpose: "travel", party_size: 2, budget_total: 260000, nights: 1, start_at: `${day}T13:00:00+09:00` })).courses[0];

  // 데이터에 따라 달라지는 구역은 계약서에서 뺀다(가게 이름 · 축제 · 지역 목록)
  const DATA = [
    "[aria-label='코스 일정']", ".jj-map", "[role=dialog]", "[aria-label*='사진']",
    // 그 동네 · 그 날짜의 데이터: 명소 이름, 공연, 숙소, 근처 행사, 예산을 바꿔 본 결과
    "[aria-labelledby='local-card'] ul", "[aria-labelledby='performance-card']", "[aria-labelledby='stay-card']",
    "[aria-labelledby='nearby-events']", "[aria-label='예산 도구'] [aria-live]",
    // 남은 돈으로 갈 만한 곳: 그날 조회된 가게들. 권할 곳이 없으면 카드째 없다(제목까지 데이터에 달렸다)
    "[aria-labelledby='leftover-card']",
    // 짠이의 이야기: 길이에 따라 "더 읽기"가 생기거나 없다
    "[aria-label='짠이의 코스 이야기']",
    // 경로 점검: 그 코스의 실제 이동 시간에 따라 생기거나 없다
    "[aria-label='경로 점검']",
  ];
  const SCENES = [
    { key: "landing", url: "/", dynamic: ["[aria-label='많이 찾는 동네']"], ready: "h1" },
    // 소개 · 브랜드 인트로 (docs/40): 예전 랜딩의 설명 섹션은 소개로 옮겼다
    { key: "about", url: "/about", dynamic: [], ready: "h1" },
    { key: "intro", url: "/intro", dynamic: [], ready: "h1" },
    { key: "plan", url: "/plan", dynamic: ["[role=radiogroup]", "[role=navigation]"] },
    { key: "plan-filled", url: "/plan?region=seoul-hongdae&purpose=date", dynamic: ["[role=radiogroup]", "[role=navigation]"], steps: 3 },
    { key: "course", url: `/course/${plain.id}`, dynamic: DATA, open: true, ready: "[aria-label='코스 일정'] article" },
    { key: "course-hop-rain", url: `/course/${hop.id}`, dynamic: DATA, ready: "[aria-label='코스 일정'] article" },
    { key: "course-trip", url: `/course/${trip.id}`, dynamic: DATA, ready: "[aria-label='코스 일정'] article" },
    { key: "course-404", url: "/course/00000000-0000-4000-8000-000000000000", dynamic: [] },
    // 제목만 기다리면 장소 목록(과 '더 보기')이 뜨기 전에 읽는다 → 목록의 첫 장소까지 기다린다
    { key: "explore", ready: "section[aria-labelledby='explore-list-heading'] li article", url: "/explore", dynamic: ["article", "[aria-label*='이벤트']", "ul"] },
    { key: "login", url: "/login", dynamic: [], ready: "main h1, main h2" },
    { key: "my", url: "/my", dynamic: [], ready: "main h1, main h2" },
    { key: "chat", url: "/chat", dynamic: [], ready: "main h1, main h2" },
    { key: "terms", url: "/terms", dynamic: [] },
    { key: "privacy", url: "/privacy", dynamic: [] },
  ].filter((s) => only.length === 0 || only.some((o) => s.key.startsWith(o)));

  const contract = existsSync(CONTRACT) ? JSON.parse(readFileSync(CONTRACT, "utf8")) : {};
  const next = {};
  const problems = [];
  const browser = await chromium.launch({ channel: "chrome" });

  for (const [vp, options] of Object.entries(VIEWPORTS)) {
    const context = await asCreator(await browser.newContext({ ...options, locale: "ko-KR" }));
    const page = await context.newPage();
    let where = "";
    const note = (kind, detail) => problems.push(`[${vp}] ${where}: ${kind} — ${detail}`);
    page.on("pageerror", (e) => note("페이지 에러", String(e).slice(0, 200)));
    // 없는 코스를 여는 화면의 404 는 의도된 것이다 (브라우저가 콘솔에도 남긴다)
    page.on("console", (m) => m.type() === "error" && !IGNORE_CONSOLE.some((r) => r.test(m.text())) && !(where === "course-404" && /404/.test(m.text())) && note("콘솔 에러", m.text().slice(0, 200)));
    page.on("requestfailed", (r) => !IGNORE_REQUEST.some((x) => x.test(r.url())) && r.failure()?.errorText !== "net::ERR_ABORTED" && note("요청 실패", `${r.url().slice(0, 120)} ${r.failure()?.errorText}`));
    page.on("response", (r) => {
      const expected404 = where === "course-404" && r.status() === 404;
      if (r.status() >= 400 && !expected404 && !IGNORE_REQUEST.some((x) => x.test(r.url()))) note(`HTTP ${r.status()}`, r.url().slice(0, 140));
    });

    for (const scene of SCENES) {
      where = scene.key;
      await page.goto(`${WEB}${scene.url}`, { timeout: 120000, waitUntil: "domcontentloaded" });
      await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => note("느림", "60초 안에 조용해지지 않음"));
      if (scene.ready) await page.locator(scene.ready).first().waitFor({ timeout: 60000 }).catch(() => note("느림", `'${scene.ready}' 가 60초 안에 나타나지 않음`));
      for (let i = 0; i < (scene.steps ?? 0); i += 1) {
        await page.getByRole("button", { name: "다음", exact: true }).click();
        await page.waitForTimeout(700);
      }
      await scrollThrough(page);
      // 늦게 오는 카드(숙소 · 공연 · 설명)가 자리를 잡을 때까지: 스켈레톤이 사라지면 끝
      await page.waitForFunction(() => document.querySelectorAll(".skeleton-shimmer").length === 0, null, { timeout: 30000 }).catch(() => undefined);
      if (scene.open) {
        // 눌러야 나오는 것들도 실제로 열어 본다: 장소 시트 · 추천 이유 · 거리뷰
        const card = page.getByLabel("코스 일정").getByRole("article").first();
        // 자세히는 카드의 ⋯ 메뉴 안에 있다 (docs/42)
        await card.getByRole("button", { name: /더보기$/ }).click().catch(() => note("동작", "'⋯' 메뉴를 열 수 없음"));
        await page.getByRole("menuitem", { name: /자세히 보기/ }).click().catch(() => note("동작", "'자세히 보기'를 열 수 없음"));
        const name = card.locator("h3 button");
        if (await name.count()) {
          await name.click();
          await page.getByRole("dialog").waitFor({ timeout: 15000 }).catch(() => note("동작", "장소 시트가 열리지 않음"));
          await page.keyboard.press("Escape");
        }
      }
      if (await page.getByText(/짠이가 실수했어요|INTERNAL_ERROR|VALIDATION_ERROR|Application error/).count()) note("에러 화면", "에러 바운더리 또는 원시 오류 코드가 보임");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 1) note("가로 넘침", `${overflow}px`);
      const seen = await inventory(page, scene.dynamic);
      if (seen.unnamed) note("접근성", `이름 없는 버튼/링크 ${seen.unnamed}개`);
      seen.broken.forEach((src) => note("깨진 이미지", src));
      const id = `${scene.key}@${vp}`;
      next[id] = { headings: seen.headings, buttons: seen.buttons, links: seen.links, labels: seen.labels };
      if (!record && contract[id]) {
        for (const bucket of ["headings", "buttons", "links", "labels"]) {
          const gone = contract[id][bucket].filter((t) => !seen[bucket].includes(t) && !Object.values(seen).flat().includes(t));
          gone.forEach((t) => note("사라진 것", `${bucket}: "${t}"`));
        }
      } else if (!record) {
        note("계약서 없음", "이 화면은 기록된 적이 없음 (--record 로 기록)");
      }
      if (shots) await page.screenshot({ path: path.join(shots, `${id}.png`), fullPage: true }).catch(() => undefined);
    }
    await context.close();
  }
  await browser.close();

  if (record) {
    if (intersect) {
      for (const [id, seen] of Object.entries(next)) {
        const before = contract[id];
        if (before) for (const bucket of Object.keys(seen)) seen[bucket] = seen[bucket].filter((t) => before[bucket]?.includes(t));
      }
    }
    writeFileSync(CONTRACT, JSON.stringify(next, null, 2) + "\n");
    const total = Object.values(next).reduce((n, s) => n + s.headings.length + s.buttons.length + s.links.length + s.labels.length, 0);
    console.log(`계약서 기록: 화면 ${Object.keys(next).length}개 · 항목 ${total}개 → ${path.relative(process.cwd(), CONTRACT)}`);
  }
  const unique = [...new Set(problems)];
  console.log(unique.length ? `\n문제 ${unique.length}건:\n` + unique.map((p) => "  " + p).join("\n") : `\n전체 사이클 통과: 화면 ${SCENES.length}개 × 뷰포트 ${Object.keys(VIEWPORTS).length}개, 문제 0건`);
  process.exit(unique.length && !record ? 1 : 0);
}

await main();
