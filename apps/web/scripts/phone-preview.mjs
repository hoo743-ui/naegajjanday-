// 모바일 화면 미리보기 (포트 3001): PC 브라우저에서 휴대폰 크기의 틀 안에 실제 사이트(3000)를 띄운다.
// 사이트는 반응형 하나라서 "모바일 버전"은 따로 없다 — 화면 폭이 좁으면 모바일 화면이 된다. 그래서 두 번째 Next 서버를
// 띄우지 않고(같은 .next 를 나눠 써서 서로 깨진다) 폭만 좁힌 틀을 보여 준다. 의존성 없음.
//   npm run preview:phone            → http://localhost:3001
//   PREVIEW_PORT=3001 PREVIEW_TARGET=http://localhost:3000 npm run preview:phone
import { createServer } from "node:http";

const PORT = Number(process.env.PREVIEW_PORT ?? 3001);
const TARGET = process.env.PREVIEW_TARGET ?? "http://localhost:3000";

const DEVICES = [
  { id: "390", label: "iPhone 15 · 390", w: 390, h: 844 },
  { id: "430", label: "iPhone 15 Pro Max · 430", w: 430, h: 932 },
  { id: "360", label: "Galaxy S · 360", w: 360, h: 780 },
];

const page = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>내가짠데이 · 모바일 미리보기</title>
<style>
  :root { color-scheme: light; --paper: #fbf8f2; --ink: #14213d; --line: #e6dfd2; --muted: #6b6f7b; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; background: #efe9dd; color: var(--ink); font: 14px/1.5 system-ui, -apple-system, "Malgun Gothic", sans-serif; display: flex; flex-direction: column; align-items: center; }
  header { width: 100%; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: center; padding: 14px 16px; }
  header b { margin-right: 8px; }
  select, input, button { font: inherit; height: 36px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); padding: 0 10px; }
  input { width: min(360px, 60vw); }
  button { cursor: pointer; }
  a { color: #2356d6; }
  .phone { margin: 4px 0 28px; padding: 12px; border-radius: 44px; background: #1b1f2a; box-shadow: 0 20px 50px rgba(20, 33, 61, .28); }
  iframe { display: block; border: 0; border-radius: 32px; background: var(--paper); }
  .hint { color: var(--muted); font-size: 12px; margin: 0 0 8px; }
</style>
</head>
<body>
<header>
  <b>모바일 미리보기</b>
  <select id="device" aria-label="기기">${DEVICES.map((d) => `<option value="${d.id}">${d.label}</option>`).join("")}</select>
  <input id="path" aria-label="주소" value="/" />
  <button id="go" type="button">열기</button>
  <button id="reload" type="button">새로고침</button>
  <a href="${TARGET}" target="_blank" rel="noreferrer">PC 화면 (${TARGET})</a>
</header>
<p class="hint">실제 사이트 ${TARGET} 를 휴대폰 폭으로 띄운 것이에요. 사이트 서버(npm run dev)가 켜져 있어야 보여요.</p>
<div class="phone"><iframe id="frame" title="모바일 화면"></iframe></div>
<script>
  const TARGET = ${JSON.stringify(TARGET)};
  const DEVICES = ${JSON.stringify(DEVICES)};
  const frame = document.getElementById("frame");
  const device = document.getElementById("device");
  const path = document.getElementById("path");
  const size = () => {
    const d = DEVICES.find((x) => x.id === device.value) || DEVICES[0];
    frame.width = d.w;
    frame.height = Math.min(d.h, window.innerHeight - 140);
  };
  const open = () => {
    const p = path.value.trim() || "/";
    frame.src = TARGET + (p.startsWith("/") ? p : "/" + p);
    history.replaceState(null, "", "?path=" + encodeURIComponent(p) + "&device=" + device.value);
  };
  const q = new URLSearchParams(location.search);
  if (q.get("path")) path.value = q.get("path");
  if (q.get("device")) device.value = q.get("device");
  device.onchange = () => { size(); open(); };
  document.getElementById("go").onclick = open;
  document.getElementById("reload").onclick = () => { frame.src = frame.src; };
  path.onkeydown = (e) => { if (e.key === "Enter") open(); };
  window.onresize = size;
  size();
  open();
</script>
</body>
</html>`;

createServer((req, res) => {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  res.end(page);
}).listen(PORT, () => console.log(`모바일 미리보기: http://localhost:${PORT}  (사이트: ${TARGET})`));
