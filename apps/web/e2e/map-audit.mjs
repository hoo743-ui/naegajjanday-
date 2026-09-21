// 지도 점검: 여러 지역의 실제 코스를 만들어 지도만 찍고, 경로 모양을 숫자로도 잰다.
//   node e2e/map-audit.mjs [outDir] [--regions=6] [--leaflet]
// "경로가 이상하게 보인다"를 눈(캡처)과 숫자(우회 배율 · 핀과 선의 간격 · 갔다가 되돌아오는 꼬리)로 함께 본다.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://localhost:8000/v1";
const outDir = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "map-audit";
const wanted = Number((process.argv.find((a) => a.startsWith("--regions=")) ?? "").replace("--regions=", "")) || 6;
mkdirSync(outDir, { recursive: true });

const meters = (a, b) => {
  const R = 6371000;
  const rad = (d) => (d * Math.PI) / 180;
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
};

/** 같은 길을 갔다가 되돌아오는 꼬리: 경로의 한 점에서 앞으로 나아갔는데 다시 그 점 가까이(8m)로 돌아오면 그 사이가 꼬리다 */
function spurMeters(coords) {
  let total = 0;
  for (let i = 0; i < coords.length - 2; i += 1) {
    let walked = 0;
    for (let j = i + 1; j < Math.min(coords.length, i + 40); j += 1) {
      walked += meters(coords[j - 1], coords[j]);
      if (j > i + 1 && walked > 25 && meters(coords[i], coords[j]) < 8) {
        total += walked;
        i = j;
        break;
      }
    }
  }
  return Math.round(total);
}

const regions = (await (await fetch(`${API}/meta/regions`)).json()).items ?? [];
const pool = regions.filter((r) => (r.place_count ?? 0) > 800 && r.slug).sort((a, b) => b.place_count - a.place_count);
const stepSize = Math.max(1, Math.floor(pool.length / wanted));
const picks = pool.filter((_, i) => i % stepSize === 0).slice(0, wanted);

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ko-KR" });
// --leaflet: 카카오 SDK 를 막아 대체 지도(Leaflet)로 떨어뜨린다 → 두 지도가 같은 코스를 같게 그리는지 본다
if (process.argv.includes("--leaflet")) await context.route("**/dapi.kakao.com/**", (r) => r.abort());
const page = await context.newPage();
const d = new Date();
d.setDate(d.getDate() + 3);

for (const region of picks) {
  const res = await fetch(`${API}/courses/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ region: region.slug, purpose: "date", party_size: 2, budget_total: 70000, start_at: `${d.toISOString().slice(0, 10)}T13:00:00+09:00`, duration_min: 300 }),
  });
  const body = await res.json();
  const course = body.courses?.[0];
  if (!course) {
    console.log(`${region.slug}: 코스 없음 (${res.status})`);
    continue;
  }
  const stops = course.stops.map((s) => [s.place.lat, s.place.lng]);
  const points = stops.map((p) => p.join(",")).join(";");
  const route = await (await fetch(`${API}/directions/walk?points=${encodeURIComponent(points)}`)).json();
  const straight = stops.slice(1).reduce((acc, p, i) => acc + meters(stops[i], p), 0);
  const gaps = stops.map((s) => Math.round(Math.min(...route.coordinates.map((c) => meters(s, c)))));
  console.log(
    `${region.slug.padEnd(28)} ${route.source}  스톱 ${stops.length}  직선 ${Math.round(straight)}m → 경로 ${route.distance_m}m (×${(route.distance_m / Math.max(straight, 1)).toFixed(2)})  핀↔선 간격 ${gaps.join("/")}m  되돌아오는 꼬리 ${spurMeters(route.coordinates)}m  꼭짓점 ${route.coordinates.length}`,
  );

  await page.goto(`${WEB}/course/${course.id}`, { timeout: 120000 });
  const map = page.locator(".jj-map").first();
  await map.waitFor({ timeout: 60000 });
  await page.waitForTimeout(4500);
  const kind = (await page.locator(".leaflet-container").count()) ? "leaflet" : "kakao";
  await map.screenshot({ path: path.join(outDir, `${region.slug}-${kind}.png`) });
}
await browser.close();
