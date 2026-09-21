// 버튼 전수 검사: 모든 화면의 누를 수 있는 것을 하나씩 **실제로 눌러 보고**, 눌렀을 때 무슨 일이 일어나는지 기록한다.
//   node e2e/button-audit.mjs [outDir] [--only=landing,course] [--token=<관리자 토큰 파일>]
// 조작 하나마다 화면을 새로 열어(서로 영향을 주지 않게) 누르고, 3초 동안 지켜본다:
//   DEAD         아무 일도 일어나지 않았다 (주소 · 요청 · 화면 · 상태 · 포커스 이동 · 클립보드 · 새 창 어느 것도)
//   ERROR        눌렀더니 페이지 에러 / 에러 화면 / 4xx·5xx 응답이 났다
//   BAD_LINK     링크의 주소가 비었거나 "#" 이다
//   (그 밖은 OK: 주소가 바뀜 · 요청이 나감 · 화면이 바뀜 · 상태가 바뀜 · 시트가 열림 · 복사됨 · 새 창)
// 누르지 않는 것: 비활성 버튼(목록으로만 남긴다), 바깥 사이트로 나가는 링크(주소 형식만 본다), 글자 입력칸.
import { chromium, devices } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const args = process.argv.slice(2);
const outDir = args.find((a) => !a.startsWith("--")) ?? "button-audit";
const only = (args.find((a) => a.startsWith("--only=")) ?? "").replace("--only=", "").split(",").filter(Boolean);
const tokenFile = (args.find((a) => a.startsWith("--token=")) ?? "").replace("--token=", "");
const mobile = args.includes("--mobile");
// --retry=<앞선 실행의 button-audit.json>: 정상이 아니었던 것만 다시 누른다 (한 탭씩 돌려 도구 탓인지 가릴 때: AUDIT_PARALLEL=1)
const retryFile = (args.find((a) => a.startsWith("--retry=")) ?? "").replace("--retry=", "");
const retry = retryFile ? JSON.parse(readFileSync(retryFile, "utf8")).filter((r) => ["ERROR", "DEAD", "GONE"].includes(r.verdict)) : null;
const retryKey = (r) => `${r.scene}|${r.tag}|${r.name}|${r.nth}`;
const retryKeys = retry ? new Set(retry.map(retryKey)) : null;
mkdirSync(outDir, { recursive: true });

const d = new Date();
d.setDate(d.getDate() + 4);
const ymd = d.toISOString().slice(0, 10);
const make = async (body) => (await (await fetch(`${API}/courses/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json()).courses[0].id;
const needsCourse = only.length === 0 || only.some((o) => "course".startsWith(o));
const courseId = !needsCourse ? "" : await make({ region: "seoul-hongdae", purpose: "date", party_size: 2, budget_total: 120000, start_at: `${ymd}T12:00:00+09:00`, duration_min: 180, alternatives: 2 });

const next = async (page, times) => {
  for (let i = 0; i < times; i += 1) {
    await page.getByRole("button", { name: "다음", exact: true }).click();
    await page.waitForTimeout(700);
  }
};
const SCENES = [
  { key: "landing", url: "/" },
  { key: "plan-1", url: "/plan" },
  { key: "plan-2", url: "/plan?region=seoul-hongdae", prepare: (p) => next(p, 1) },
  { key: "plan-3", url: "/plan?region=seoul-hongdae&purpose=date", prepare: (p) => next(p, 2) },
  { key: "plan-4", url: "/plan?region=seoul-hongdae&purpose=date", prepare: (p) => next(p, 3) },
  { key: "course", url: `/course/${courseId}`, ready: "[aria-label='코스 일정'] article" },
  { key: "explore", url: "/explore", ready: "main article" },
  { key: "login", url: "/login" },
  { key: "my", url: "/my" },
  { key: "chat", url: "/chat" },
  { key: "terms", url: "/terms" },
  { key: "not-found", url: "/no-such-page" },
  ...(tokenFile ? ["", "/regions", "/places", "/attractions", "/events", "/banners", "/scoring", "/recommendations", "/users"].map((s) => ({ key: `admin${s.replace("/", "-")}`, url: `/admin${s}`, admin: true })) : []),
  // --only=admin 은 admin 으로 시작하는 모든 화면, --only=admin$ 는 그 화면 하나(토큰이 15분이라 관리자 화면은 하나씩 돈다)
].filter((s) => (only.length === 0 || only.some((o) => (o.endsWith("$") ? s.key === o.slice(0, -1) : s.key.startsWith(o)))) && (!retry || retry.some((r) => r.scene === s.key)));

const SELECTOR = "button, a[href], [role=tab], [role=radio], [role=checkbox], [role=switch], [role=menuitem], summary, input[type=checkbox], input[type=radio], label:has(input.sr-only)";

/** 화면의 누를 수 있는 것들: [{name, nth, tag, href, disabled, external}] — 다시 열어도 (name, nth) 로 같은 것을 찾는다 */
const collect = (page) =>
  page.evaluate((selector) => {
    const seen = new Map();
    const out = [];
    for (const el of document.querySelectorAll(selector)) {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (rect.width < 2 || rect.height < 2 || style.visibility === "hidden" || style.display === "none") continue;
      if (el.closest("[aria-hidden='true'], [inert], nextjs-portal")) continue;
      if (el.tagName === "INPUT" && el.closest("label")) continue; // 감싼 label 을 누른다
      const name = (el.getAttribute("aria-label") || el.innerText || el.getAttribute("title") || el.value || "").replace(/\s+/g, " ").trim().slice(0, 60);
      const key = `${el.tagName}|${name}`;
      const nth = seen.get(key) ?? 0;
      seen.set(key, nth + 1);
      const href = el.tagName === "A" ? el.getAttribute("href") : null;
      out.push({
        name,
        nth,
        tag: el.tagName.toLowerCase(),
        href,
        disabled: el.disabled === true || el.getAttribute("aria-disabled") === "true",
        external: href ? /^(https?:)?\/\//.test(href) && !href.startsWith(location.origin) : false,
        newTab: el.getAttribute("target") === "_blank",
        chosen:
          ["aria-checked", "aria-pressed", "aria-selected"].some((a) => el.getAttribute(a) === "true") ||
          ![null, "false"].includes(el.getAttribute("aria-current")) ||
          el.querySelector?.("input:checked") != null,
      });
    }
    return out;
  }, SELECTOR);

const locate = (page, control) =>
  page.evaluateHandle(
    ({ selector, control }) => {
      let n = 0;
      for (const el of document.querySelectorAll(selector)) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) continue;
        if (el.closest("[aria-hidden='true'], [inert], nextjs-portal")) continue;
        if (el.tagName === "INPUT" && el.closest("label")) continue;
        const name = (el.getAttribute("aria-label") || el.innerText || el.getAttribute("title") || el.value || "").replace(/\s+/g, " ").trim().slice(0, 60);
        if (el.tagName.toLowerCase() === control.tag && name === control.name) {
          if (n === control.nth) return el;
          n += 1;
        }
      }
      return null;
    },
    { selector: SELECTOR, control },
  );

const PARALLEL = Number(process.env.AUDIT_PARALLEL ?? 3); // 한 번에 여는 탭 수 (조작 하나마다 화면을 새로 연다)
const browser = await chromium.launch({ channel: "chrome" });
const adminToken = tokenFile ? readFileSync(tokenFile, "utf8").trim().split(/\r?\n/).pop().trim() : null;
const results = [];

async function open(context, scene) {
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.__fx = { dialogs: [], copied: 0, opened: 0, mutations: 0 };
    window.confirm = (m) => (window.__fx.dialogs.push(String(m)), false); // 지우기 같은 되돌릴 수 없는 일은 "취소"로 답한다
    window.alert = (m) => void window.__fx.dialogs.push(String(m));
    window.open = () => ((window.__fx.opened += 1), null);
    if (navigator.clipboard) navigator.clipboard.writeText = async () => void (window.__fx.copied += 1);
    if (navigator.share) navigator.share = async () => void (window.__fx.copied += 1);
  });
  await page.goto(`${WEB}${scene.url}`, { timeout: 120000, waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => undefined); // 스트리밍 · 폴링이 있는 화면은 끝내 조용해지지 않는다
  if (scene.ready) await page.locator(scene.ready).first().waitFor({ timeout: 60000 }).catch(() => undefined);
  if (scene.prepare) await scene.prepare(page);
  await page.waitForTimeout(800);
  return page;
}

for (const scene of SCENES) {
  const context = await browser.newContext({ ...(mobile ? devices["Pixel 7"] : { viewport: { width: 1440, height: 900 } }), locale: "ko-KR" });
  // 공연 조회는 17초가 걸리고 이 검사의 대상이 아니다
  await context.route("**/v1/performances**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], partial: false }) }));
  if (scene.admin && adminToken) await context.route("**/v1/auth/refresh", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: adminToken, token_type: "Bearer", expires_in: 900 }) }));
  // 관리자 화면에는 확인창 없이 실데이터를 바꾸는 버튼이 있다(승인 · 반려 · 일시정지 · 저장 · 지우기). 모든 버튼을 누르는 검사가
  // 장소 80만 곳의 DB 를 고치면 안 된다 → 읽기(GET) 말고는 서버에 보내지 않는다. 요청이 나갔다는 사실은 그대로 "효과"로 기록된다.
  if (scene.admin) {
    await context.route("**/v1/**", (route) => {
      const method = route.request().method();
      if (method === "GET" || method === "OPTIONS" || /\/auth\/refresh/.test(route.request().url())) return route.fallback();
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
  }
  const first = await open(context, scene);
  // 코스 화면의 이름은 코스마다 다르다(가게 이름이 들어간다) → 그 화면은 통째로 다시 본다
  const controls = (await collect(first)).filter((c) => !retryKeys || scene.key === "course" || retryKeys.has(retryKey({ scene: scene.key, ...c })));
  await first.close();
  console.log(`\n[${scene.key}] 누를 수 있는 것 ${controls.length}개`);

  const rows = controls.map((control) => ({ scene: scene.key, ...control, verdict: "OK", effect: "" }));
  results.push(...rows);
  const press = async (row) => {
    const control = row;
    if (control.disabled) {
      row.verdict = "DISABLED";
      return;
    }
    if (control.tag === "a") {
      if (!control.href || control.href === "#" || control.href.startsWith("javascript")) {
        row.verdict = "BAD_LINK";
        row.effect = `href="${control.href}"`;
        return;
      }
      if (control.external || control.newTab) {
        row.effect = `바깥 링크 → ${control.href.slice(0, 80)}`;
        return; // 남의 사이트는 누르지 않는다
      }
    }
    const page = await open(context, scene);
    const problems = [];
    const requests = [];
    page.on("pageerror", (e) => problems.push(`페이지 에러: ${String(e).slice(0, 140)}`));
    page.on("request", (r) => /\/v1\//.test(r.url()) && requests.push(`${r.method()} ${r.url().split("/v1")[1].slice(0, 60)}`));
    page.on("response", (r) => r.status() >= 400 && /\/v1\//.test(r.url()) && !/auth\/refresh|\/me\b/.test(r.url()) && problems.push(`${r.status()} ${r.url().split("/v1")[1].slice(0, 60)}`));
    try {
      let el = (await locate(page, control)).asElement();
      if (!el) {
        row.verdict = "GONE";
        row.effect = "다시 열었더니 없다 (데이터에 따라 달라지는 것)";
        await page.close();
        return;
      }
      await el.scrollIntoViewIfNeeded().catch(() => undefined);
      const before = await page.evaluate((node) => {
        window.__fx.mutations = 0;
        window.__fx.state = ["aria-pressed", "aria-expanded", "aria-selected", "aria-checked", "data-state", "open"].map((a) => node.getAttribute(a)).join("|") + "|" + (node.querySelector?.("input")?.checked ?? node.checked ?? "");
        new MutationObserver((list) => {
          for (const m of list) if (m.type === "childList" ? m.addedNodes.length + m.removedNodes.length > 0 : true) window.__fx.mutations += 1;
        }).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-pressed", "aria-expanded", "aria-selected", "aria-checked", "data-state", "open", "hidden", "aria-current", "aria-invalid"] });
        return { url: location.href, scroll: window.scrollY, focus: document.activeElement?.outerHTML.slice(0, 80) };
      }, el);
      await page.waitForTimeout(500);
      const noise = await page.evaluate(() => window.__fx.mutations); // 누르기 전에 혼자 바뀌는 양(스트리밍 문장 등)
      await el.click({ timeout: 8000 }).catch(async (e) => {
        if (!/not attached|detached/.test(String(e))) throw e;
        el = (await locate(page, control)).asElement(); // 화면이 다시 그려져 떨어졌다 → 같은 것을 다시 찾아 누른다
        if (!el) throw e;
        await el.click({ timeout: 8000 });
      });
      await page.waitForTimeout(2600);
      // 다른 주소로 가는 링크: 개발 서버는 처음 여는 화면을 그때 컴파일한다(여러 탭이 나눠 쓰면 더 느리다) → 주소가 바뀔 때까지 기다린다
      const goesElsewhere = control.tag === "a" && control.href && new URL(control.href, before.url).href.split("#")[0] !== before.url.split("#")[0];
      if (goesElsewhere && page.url() === before.url) await page.waitForURL((u) => u.href !== before.url, { timeout: 45000 }).catch(() => undefined);
      const after = await page
        .evaluate((node) => {
          const state = node.isConnected ? ["aria-pressed", "aria-expanded", "aria-selected", "aria-checked", "data-state", "open"].map((a) => node.getAttribute(a)).join("|") + "|" + (node.querySelector?.("input")?.checked ?? node.checked ?? "") : "(사라짐)";
          return { url: location.href, scroll: window.scrollY, fx: window.__fx, state, errorScreen: /짠이가 실수했어요|INTERNAL_ERROR/.test(document.body.innerText), dialogOpen: document.querySelector("[role=dialog], [role=menu], [role=listbox]") !== null };
        }, el)
        .catch(() => ({ url: page.url(), navigated: true, fx: { dialogs: [], copied: 0, opened: 0, mutations: 99 }, state: "(이동)" }));
      const effects = [];
      if (after.url !== before.url || after.navigated) effects.push(`주소 → ${after.url.replace(WEB, "")}`.slice(0, 70));
      if (requests.length) effects.push(`요청 ${requests[0]}${requests.length > 1 ? ` 외 ${requests.length - 1}` : ""}`);
      if (after.state !== undefined && after.state !== (await page.evaluate(() => window.__fx.state).catch(() => after.state))) effects.push("상태 바뀜");
      if (after.dialogOpen) effects.push("시트 · 메뉴 열림");
      if (after.fx.mutations - noise > 0) effects.push(`화면 바뀜(${after.fx.mutations - noise})`);
      if (after.fx.copied) effects.push("복사 · 공유");
      if (after.fx.opened) effects.push("새 창");
      if (after.fx.dialogs.length) effects.push(`확인창: ${after.fx.dialogs[0].slice(0, 40)}`);
      if (Math.abs((after.scroll ?? 0) - before.scroll) > 40) effects.push("스크롤 이동");
      if (after.errorScreen) problems.push("에러 화면");
      row.effect = effects.join(" · ");
      if (problems.length) {
        row.verdict = "ERROR";
        row.effect = `${problems.join(" / ")} ← ${row.effect}`;
      } else if (effects.length === 0) {
        // 이미 골라져 있는 것을 다시 누르면 아무 일도 없는 게 맞다. 단, 그렇다고 화면이 말해 줄 때만(aria-checked · pressed · selected · current)
        row.verdict = control.chosen ? "CHOSEN" : "DEAD";
      }
    } catch (e) {
      row.verdict = "ERROR";
      row.effect = `누를 수 없다: ${String(e).split("\n")[0].slice(0, 140)}`;
    }
    await page.close();
    if (!["OK", "CHOSEN"].includes(row.verdict)) console.log(`  ${row.verdict.padEnd(8)} ${control.tag} "${control.name}" ${row.effect}`);
  };
  const queue = [...rows];
  await Promise.all(
    Array.from({ length: PARALLEL }, async () => {
      for (let row = queue.shift(); row; row = queue.shift()) await press(row).catch((e) => Object.assign(row, { verdict: "ERROR", effect: `검사 실패: ${String(e).slice(0, 120)}` }));
    }),
  );
  await context.close();
}
await browser.close();

const count = (v) => results.filter((r) => r.verdict === v).length;
const lines = [`조작 ${results.length}개 · 정상 ${count("OK")} · 아무 일도 없음 ${count("DEAD")} · 오류 ${count("ERROR")} · 잘못된 링크 ${count("BAD_LINK")} · 이미 골라진 것 ${count("CHOSEN")} · 비활성 ${count("DISABLED")} · 다시 못 찾음 ${count("GONE")}`];
for (const verdict of ["ERROR", "DEAD", "BAD_LINK", "DISABLED", "GONE"]) {
  const rows = results.filter((r) => r.verdict === verdict);
  if (rows.length) lines.push(`\n${verdict}`, ...rows.map((r) => `  [${r.scene}] ${r.tag} "${r.name}" ${r.effect}`));
}
console.log("\n" + lines.join("\n"));
writeFileSync(path.join(outDir, "button-audit.json"), JSON.stringify(results, null, 1));
writeFileSync(path.join(outDir, "button-audit.txt"), lines.join("\n") + "\n");
process.exit(count("ERROR") + count("DEAD") + count("BAD_LINK") > 0 ? 1 : 0);
