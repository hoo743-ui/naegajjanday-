// 관리자 › 장소 › 사진 탭: 파일을 고르면 미리보기가 뜨고, 올리면 API 가 기대하는 모양(multipart: file + make_cover)으로 나가는지.
// 실제 가게에 시험 사진이 남으면 안 되므로 업로드 요청은 가로채서 내용만 확인한다 (저장 · 서빙은 API 통합 테스트가 본다).
//   node e2e/upload-audit.mjs <관리자 토큰 파일> [outDir]      토큰: uv run python -m app.cli create-admin --email … --print-token
import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const token = readFileSync(process.argv[2], "utf8").trim().split(/\r?\n/).pop().trim();
const outDir = process.argv[3] ?? "upload-audit";
mkdirSync(outDir, { recursive: true });
const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ✓" : "  ✗"} ${what}`);
  if (!ok) failures.push(what);
};

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
await context.route("**/v1/auth/refresh", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: token, token_type: "Bearer", expires_in: 900 }) }));
let sent = null;
let listed = null;
await context.route("**/v1/admin/places/*/photos", async (route) => {
  const request = route.request();
  sent = { method: request.method(), type: request.headers()["content-type"] ?? "", body: request.postDataBuffer() ?? Buffer.alloc(0) };
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(listed) });
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
page.on("response", async (r) => {
  if (r.url().includes("/v1/admin/places?") && r.ok() && !listed) listed = (await r.json()).items?.[0] ?? null;
});

await page.goto(`${WEB}/admin/places`, { timeout: 120000 });
await page.getByRole("tab", { name: "승인됨" }).click();
const row = page.locator("table tbody tr").first();
await row.waitFor({ timeout: 60000 });
await row.click();
await page.getByRole("tab", { name: "사진" }).click();
const panel = page.getByRole("tabpanel", { name: "사진" });
await panel.getByText("지금 보이는 사진").waitFor({ timeout: 30000 });
check(true, "사진 탭이 열린다");
check(await panel.getByRole("button", { name: "사진 올리기" }).isDisabled(), "파일을 고르기 전에는 올리기 버튼이 잠겨 있다");

await panel.locator("input[type=file]").setInputFiles({ name: "note.txt", mimeType: "text/plain", buffer: Buffer.from("not a picture") });
check((await panel.getByText("JPEG · PNG · WebP 사진만 올릴 수 있어요.").count()) > 0, "사진이 아닌 파일은 올리기 전에 막는다");

await panel.locator("input[type=file]").setInputFiles({ name: "shop.png", mimeType: "image/png", buffer: PNG });
await panel.getByAltText("올릴 사진 미리보기").waitFor({ timeout: 10000 });
check(true, "고른 사진의 미리보기가 보인다");
await page.screenshot({ path: path.join(outDir, "upload-preview.png") });

await panel.getByRole("button", { name: "사진 올리기" }).click();
await panel.getByText("사진을 올렸어요").waitFor({ timeout: 30000 });
check(sent?.method === "POST" && sent.type.startsWith("multipart/form-data"), "multipart POST 로 나간다");
const text = sent?.body.toString("latin1") ?? "";
check(/name="file"; filename="shop\.png"/.test(text) && sent.body.includes(PNG), "file 필드에 사진 바이트가 그대로 실린다");
check(/name="make_cover"\r\n\r\ntrue/.test(text), "make_cover=true (대표 사진으로 쓰기)가 함께 간다");
check(errors.length === 0, `페이지 에러 0건${errors.length ? " → " + errors[0] : ""}`);

await browser.close();
console.log(failures.length ? `\n실패 ${failures.length}건` : "\n모두 통과");
process.exit(failures.length ? 1 : 0);
