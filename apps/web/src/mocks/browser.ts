import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

const worker = setupWorker(...handlers);

export async function startWorker(): Promise<void> {
  await worker.start({
    serviceWorker: { url: "/mockServiceWorker.js" },
    // API 가 아닌 요청(_next, 폰트, 지도 SDK 등)은 조용히 통과
    onUnhandledRequest(request, print) {
      const api = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1").replace(/\/$/, "");
      if (request.url.startsWith(api)) print.warning();
    },
    quiet: true,
  });
  console.info("%c[MSW] 목 API 사용 중 — 실제 백엔드로 나가는 요청이 없습니다", "color:#E29A14;font-weight:bold");
}
