// 운영 빌드로 로컬에서 보기 (docs/45): npm run preview:prod  → http://localhost:3100
//
// `next dev` 는 화면을 처음 열 때마다 그 자리에서 컴파일한다(OneDrive 안에서 코스 결과 첫 방문 73초, 내 코스 40초),
// 자바스크립트도 압축하지 않은 6.4MB 다. 사용자가 받는 속도를 보려면 운영 빌드를 봐야 한다.
// 그런데 이 폴더에서 `next build` 를 돌리면 돌고 있는 dev 서버의 .next 를 깨뜨린다(docs/40 사고) →
// 소스를 OneDrive 밖(%LOCALAPPDATA%\naegajjanday\webprod)에 복사하고 node_modules 는 연결만 해서 거기서 빌드한다.
// dev 서버(3000)와 그 .next 는 건드리지 않는다. API 의 CORS_ORIGINS 에 http://localhost:3100 이 있어야 한다.
import { cpSync, existsSync, mkdirSync, rmSync, symlinkSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync, spawn } from "node:child_process";

const src = resolve(import.meta.dirname, "..");
const base = process.env.LOCALAPPDATA ?? join(homedir(), ".cache");
const dst = join(base, "naegajjanday", "webprod");
const SKIP = new Set(["node_modules", ".next", "test-results", "playwright-report"]);
const port = process.env.PORT ?? "3100";

mkdirSync(dst, { recursive: true });
if (process.platform === "win32") {
  // fs.cpSync 는 이 경로(한글 폴더 + OneDrive)에서 node 자체가 0xC0000005 로 죽는다 → robocopy /MIR (지운 파일도 따라 지운다)
  const r = spawnSync("robocopy", [src, dst, "/MIR", "/XD", ...SKIP, "/NFL", "/NDL", "/NJH", "/NJS", "/NP"], { stdio: "inherit" });
  if ((r.status ?? 16) >= 8) process.exit(r.status ?? 1); // robocopy: 0~7 은 성공
} else {
  // 지난번 복사본의 소스는 지운다(지운 파일이 남지 않게). node_modules 연결과 .next 캐시는 둔다
  for (const name of ["src", "public"]) rmSync(join(dst, name), { recursive: true, force: true });
  cpSync(src, dst, { recursive: true, filter: (p) => !SKIP.has(p.slice(src.length + 1).split(/[\\/]/)[0]) });
}
if (!existsSync(join(dst, "node_modules"))) symlinkSync(join(src, "node_modules"), join(dst, "node_modules"), "junction");

const npx = process.platform === "win32" ? "npx.cmd" : "npx";
console.log(`[preview:prod] ${dst} 에서 빌드`);
// standalone 복사 단계의 EPERM(symlink) 경고는 Docker 용이라 로컬 미리보기에는 상관없다
const build = spawnSync(npx, ["next", "build"], { cwd: dst, stdio: "inherit", shell: process.platform === "win32" });
if (!existsSync(join(dst, ".next", "BUILD_ID"))) process.exit(build.status ?? 1);
console.log(`[preview:prod] http://localhost:${port}`);
spawn(npx, ["next", "start", "-p", port], { cwd: dst, stdio: "inherit", shell: process.platform === "win32" });
