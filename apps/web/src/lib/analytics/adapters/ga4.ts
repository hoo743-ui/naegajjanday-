import type { AnalyticsAdapter } from "../events";
import { loadScript } from "./load-script";

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

export function createGa4(measurementId: string): AnalyticsAdapter {
  return {
    name: "ga4",
    async init() {
      const layer = (window.dataLayer = window.dataLayer ?? []);
      window.gtag = function gtag(...args: unknown[]) {
        layer.push(args);
      };
      window.gtag("js", new Date());
      // SPA 라우팅은 page() 에서 직접 보낸다
      window.gtag("config", measurementId, { send_page_view: false });
      await loadScript(`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`);
    },
    track(event, props) {
      window.gtag?.("event", event, props);
    },
    page(path, props) {
      window.gtag?.("event", "page_view", { page_path: path, page_location: window.location.href, ...props });
    },
    identify(userId) {
      window.gtag?.("config", measurementId, { user_id: userId, send_page_view: false });
    },
  };
}
