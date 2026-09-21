// 대량 검증: 전국의 동네 × 목적 × 시각 × 예산 × 이동수단을 섞은 코스 수백 개를 실제 API 로 만들고,
// 결과 화면을 진짜 크롬에서 열어 "서비스가 한 약속"을 하나씩 확인한다. 통과/실패가 아니라 **몇 %가 어떤 약속을 어겼는지**를 센다.
//   node e2e/bulk-audit.mjs [outDir] [--n=300] [--workers=4] [--seed=7]
// 확인하는 약속 (코드 · 뜻):
//   NO_COURSE        코스를 만들지 못했다(예산이 너무 적다는 정직한 거절은 세지 않는다)
//   FEW_STOPS        한 곳뿐인 코스 (짧은 약속 제외)
//   OVER_BUDGET      합계가 예산을 넘는데 화면이 그 사실을 말하지 않는다
//   SUM_MISMATCH     영수증의 합계 ≠ 장소 금액의 합, 또는 화면의 남은 돈 ≠ 예산 − 합계
//   LEFT_UNSPOKEN    예산의 40% 이상이 남았는데 화면이 남는 돈으로 할 것을 아무것도 권하지 않는다
//   LONG_WALK        걸어서 25분이 넘는 구간
//   SAME_KIND_TWICE  같은 업종이 연달아 (카페 → 카페)
//   TIME_ORDER       도착 시각이 앞 장소보다 이르다
//   ESTIMATE_UNLABELED 추정가인데 화면에 "평균가" 표시가 없다
//   STANDIN_UNLABELED  그 가게 사진이 아닌데 "예시 사진" 표시가 없다
//   PIN_MISSING      지도의 핀 수 ≠ 장소 수, 또는 핀이 지도 밖에 있다
//   NIGHT_UNSAID     밤 코스인데 영업시간을 추정했다는 안내가 없다
//   PAGE_ERROR · ERROR_SCREEN · OVERFLOW  화면이 깨졌다
import { chromium, devices } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const args = process.argv.slice(2);
const opt = (name, fallback) => Number((args.find((a) => a.startsWith(`--${name}=`)) ?? "").split("=")[1] ?? fallback);
const outDir = args.find((a) => !a.startsWith("--")) ?? "bulk-audit";
const N = opt("n", 300);
const WORKERS = opt("workers", 4);
let seed = opt("seed", 7);
mkdirSync(outDir, { recursive: true });

// 같은 seed 면 같은 시나리오: 고친 뒤에 같은 코스들로 다시 잰다
const rand = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
const pick = (list) => list[Math.floor(rand() * list.length)];
// 요청 하나가 늦거나 끊겨도 검증 전체가 죽지 않는다: 그 코스를 TIMEOUT 으로 세고 다음으로 간다
const json = async (url, init) => {
  try {
    const res = await fetch(url, { ...init, signal: AbortSignal.timeout(150000) });
    return { status: res.status, body: await res.json().catch(() => null) };
  } catch (e) {
    return { status: 0, body: { code: "TIMEOUT", detail: String(e).slice(0, 80) } };
  }
};

const regions = (await json(`${API}/meta/regions`)).body.items.filter((r) => r.level >= 2 && r.place_count >= 300);
const purposes = (await json(`${API}/meta/purposes`)).body.items;
const day = new Date();
day.setDate(day.getDate() + 4);
const ymd = day.toISOString().slice(0, 10);

const scenarios = [];
for (let i = 0; i < N; i += 1) {
  const purpose = pick(purposes);
  const region = pick(regions);
  const party = purpose.code === "solo" ? 1 : purpose.code === "date" ? 2 : pick([2, 2, 3, 4]);
  const per = pick([purpose.budget_per_person.min, purpose.budget_per_person.typical, purpose.budget_per_person.typical, Math.round(purpose.budget_per_person.max * 0.8), purpose.budget_per_person.max * 2]);
  const start = pick(["11:30", "12:00", "14:30", "15:00", "18:30", "18:30", "19:30", "22:30", "01:30"]);
  const body = {
    region: region.slug,
    purpose: purpose.code,
    party_size: party,
    budget_total: Math.max(5000, Math.round((per * party) / 1000) * 1000),
    start_at: `${ymd}T${start}:00+09:00`,
    transport: pick(["walk", "walk", "walk", "transit", "car"]),
    style: pick(["efficient", "efficient", "fun"]),
    alternatives: 0,
  };
  if (rand() < 0.25) body.duration_min = pick([120, 180, 240, 360, 480]);
  if (rand() < 0.12) body.conditions = ["rain"];
  if (rand() < 0.12 && purpose.code !== "family") body.extras = ["BAR"];
  if (rand() < 0.08) body.nights = 1;
  scenarios.push({ i, region: region.name, body });
}

const browser = await chromium.launch({ channel: "chrome" });
const results = [];
let done = 0;

async function inspect(page, scenario, course, request) {
  const found = [];
  const add = (code, detail) => found.push({ code, detail });
  const stops = course.stops;
  const budget = request.budget_total;
  const total = course.totals.price;
  const night = ((h) => h >= 21 || h < 5)(Number(request.start_at.slice(11, 13)));

  // ── API 가 준 코스 자체 ──
  if (stops.length < 2 && !(scenario.body.duration_min && scenario.body.duration_min <= 120)) add("FEW_STOPS", `${stops.length}곳`);
  if (total !== stops.reduce((s, x) => s + x.est_price, 0)) add("SUM_MISMATCH", `합계 ${total} ≠ 장소 합`);
  stops.forEach((s, k) => {
    if (k > 0 && new Date(s.arrive_at) < new Date(stops[k - 1].leave_at)) add("TIME_ORDER", s.place.name);
    if (k > 0 && s.from_prev.mode === "walk" && s.from_prev.travel_min > 25) add("LONG_WALK", `→ ${s.place.name} ${s.from_prev.travel_min}분`);
    if (k > 0 && s.place.category === stops[k - 1].place.category && s.role === stops[k - 1].role) add("SAME_KIND_TWICE", `${stops[k - 1].place.name} → ${s.place.name}`);
  });

  // ── 화면 ──
  const errors = [];
  const onError = (e) => errors.push(String(e).slice(0, 160));
  page.on("pageerror", onError);
  // "이런 건 어때요?"는 코스가 그려진 뒤에 온다 → 그 응답까지 기다린 다음에 화면을 읽는다
  const offered = budget - total > 0 ? page.waitForResponse((r) => r.url().includes("/suggestions"), { timeout: 30000 }).catch(() => null) : null;
  await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
  const ready = await page.getByLabel("코스 일정").locator("article").first().waitFor({ timeout: 60000 }).then(() => true, () => false);
  if (!ready) {
    add("ERROR_SCREEN", "코스 일정이 60초 안에 그려지지 않았다");
    page.off("pageerror", onError);
    return found;
  }
  await offered;
  // 지도는 SDK 를 받아 온 뒤에 그려진다: 핀을 세기 전에 핀이 생길 때까지 기다린다. 끝내 안 생기면 "핀 0/0"으로 남는다
  // (핀은 있는데 상자 밖이면 "핀 5/7" — 앞의 것은 지도 로딩, 뒤의 것은 진짜 결함이다)
  await page.locator(".jj-pin-drop").first().waitFor({ state: "attached", timeout: 20000 }).catch(() => undefined);
  await page.waitForTimeout(1500);
  const seen = await page.evaluate(() => {
    const text = document.body.innerText;
    const cards = [...document.querySelectorAll("[aria-label='코스 일정'] article")];
    const map = document.querySelector(".jj-map")?.getBoundingClientRect();
    const drops = [...document.querySelectorAll(".jj-pin-drop")].map((el) => el.getBoundingClientRect());
    return {
      text,
      cards: cards.map((c) => ({ text: c.innerText, hasPhoto: c.querySelector("img") !== null })),
      pins: drops.length,
      pinsInside: map ? drops.filter((r) => r.left >= map.left - 2 && r.right <= map.right + 2 && r.top >= map.top - 2 && r.bottom <= map.bottom + 2).length : 0,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      errorScreen: /짠이가 실수했어요|INTERNAL_ERROR/.test(text),
    };
  });
  page.off("pageerror", onError);
  if (errors.length) add("PAGE_ERROR", errors[0]);
  if (seen.errorScreen) add("ERROR_SCREEN", "에러 화면");
  if (seen.overflow > 1) add("OVERFLOW", `${seen.overflow}px`);
  if (seen.pins !== stops.length || seen.pinsInside !== stops.length) add("PIN_MISSING", `핀 ${seen.pinsInside}/${seen.pins} · 장소 ${stops.length}`);

  const left = budget - total;
  const won = (n) => `${n.toLocaleString("ko-KR")}원`;
  if (left < 0 && !/예산 초과|예산보다|초과해요/.test(seen.text)) add("OVER_BUDGET", won(-left));
  if (left >= 0 && !seen.text.includes(won(left))) add("SUM_MISMATCH", `화면에 남은 돈 ${won(left)} 이 없다`);
  if (budget > 0 && left / budget >= 0.4 && !/이런 건 어때요|남은 돈으로/.test(seen.text)) add("LEFT_UNSPOKEN", `${Math.round((left / budget) * 100)}% 남음 (${won(left)})`);
  stops.forEach((s, k) => {
    const card = seen.cards[k]?.text ?? "";
    if (s.place.price_is_estimated && s.est_price > 0 && !card.includes("평균가")) add("ESTIMATE_UNLABELED", s.place.name);
    if (!s.place.thumbnail_url && seen.cards[k]?.hasPhoto && !card.includes("예시 사진")) add("STANDIN_UNLABELED", s.place.name);
  });
  if (night && !seen.text.includes("가기 전에 영업 여부")) add("NIGHT_UNSAID", request.start_at.slice(11, 16));
  return found;
}

async function worker(id) {
  const context = await browser.newContext(id % 2 === 0 ? { viewport: { width: 1440, height: 900 }, locale: "ko-KR" } : { ...devices["Pixel 7"], locale: "ko-KR" });
  // 공연 조회(KOPIS)는 요청당 17초가 걸리고 이번 검증의 대상이 아니다. 단일 프로세스 API 에서 코스 생성을 줄 세우므로 막는다
  await context.route("**/v1/performances**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], partial: false }) }));
  const page = await context.newPage();
  for (;;) {
    const scenario = scenarios.shift();
    if (!scenario) break;
    const made = await json(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scenario.body) });
    const row = { ...scenario, findings: [] };
    if (made.status !== 200) {
      // "이 예산으로는 어렵다"는 정직한 거절이다. 그 밖의 실패만 센다
      if (made.body?.code !== "BUDGET_TOO_LOW") row.findings.push({ code: "NO_COURSE", detail: `${made.status} ${made.body?.code ?? ""} ${made.body?.detail ?? ""}`.slice(0, 140) });
      row.refused = made.body?.code ?? String(made.status);
    } else {
      for (const course of made.body.courses) {
        const request = { ...scenario.body, budget_total: made.body.courses.length > 1 ? (await json(`${API}/courses/${course.id}`)).body.request.budget_total : scenario.body.budget_total };
        if (made.body.courses.length > 1) request.start_at = (await json(`${API}/courses/${course.id}`)).body.request.start_at;
        try {
          row.findings.push(...(await inspect(page, scenario, course, request)));
        } catch (e) {
          row.findings.push({ code: "PAGE_ERROR", detail: String(e).slice(0, 160) });
        }
        row.summary = `${course.stops.map((s) => s.place.name).join(" → ")} · ${course.totals.price.toLocaleString()}/${request.budget_total.toLocaleString()}`;
      }
    }
    results.push(row);
    done += 1;
    if (done % 20 === 0) {
      console.log(`  ${done}/${N}`);
      writeFileSync(path.join(outDir, "bulk-audit.json"), JSON.stringify(results, null, 1)); // 중간에 끊겨도 여기까지는 남는다
    }
  }
  await context.close();
}

await Promise.all(Array.from({ length: WORKERS }, (_, k) => worker(k)));
await browser.close();

const byCode = new Map();
for (const r of results) for (const f of new Map(r.findings.map((x) => [x.code, x])).values()) byCode.set(f.code, [...(byCode.get(f.code) ?? []), { ...f, r }]);
const clean = results.filter((r) => r.findings.length === 0 && !r.refused).length;
const refused = results.filter((r) => r.refused === "BUDGET_TOO_LOW").length;
const lines = [`코스 ${results.length}개 · 약속을 모두 지킨 코스 ${clean} (${((clean / Math.max(1, results.length - refused)) * 100).toFixed(1)}%) · 예산이 적어 정직하게 거절 ${refused}`];
for (const [code, list] of [...byCode.entries()].sort((a, b) => b[1].length - a[1].length)) {
  lines.push(`\n${code}  ${list.length}건 (${((list.length / results.length) * 100).toFixed(1)}%)`);
  for (const x of list.slice(0, 6)) lines.push(`   - ${x.r.region} · ${x.r.body.purpose} · ${x.r.body.start_at.slice(11, 16)} · ${x.r.body.transport} · ${x.r.body.budget_total.toLocaleString()}원 → ${x.detail}`);
}
console.log("\n" + lines.join("\n"));
writeFileSync(path.join(outDir, "bulk-audit.json"), JSON.stringify(results, null, 1));
writeFileSync(path.join(outDir, "bulk-audit.txt"), lines.join("\n") + "\n");
