// 진단용: 모바일 뷰포트에서 화면 밖으로 삐져나온 요소를 찾아 출력한다.  node e2e/overflow-probe.mjs /explore /plan …
import { chromium, devices } from "@playwright/test";

const base = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const paths = process.argv.slice(2);
const browser = await chromium.launch({ channel: process.env.E2E_CHANNEL ?? "chrome" });
const context = await browser.newContext({ ...devices["Pixel 7"], locale: "ko-KR" });
for (const path of paths) {
  const page = await context.newPage();
  await page.goto(base + path, { waitUntil: "networkidle", timeout: 90_000 }).catch(() => undefined);
  await page.waitForTimeout(2500);
  const report = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const offenders = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.right <= vw + 1) continue;
      // 가로 스크롤 컨테이너 안에 있는 것은 정상이다
      let scroller = el.parentElement;
      let inside = false;
      while (scroller) {
        const ox = getComputedStyle(scroller).overflowX;
        if ((ox === "auto" || ox === "scroll" || ox === "hidden") && scroller !== document.body && scroller !== document.documentElement) {
          inside = true;
          break;
        }
        scroller = scroller.parentElement;
      }
      if (!inside) offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 70)} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
    }
    return { vw, scrollWidth: document.documentElement.scrollWidth, offenders: offenders.slice(0, 8) };
  });
  console.log(path, JSON.stringify(report, null, 1));
  await page.close();
}
await browser.close();
