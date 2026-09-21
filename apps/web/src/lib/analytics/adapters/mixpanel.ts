import type { AnalyticsAdapter } from "../events";
import { loadScript } from "./load-script";

interface MixpanelLike {
  init(token: string, config?: Record<string, unknown>): void;
  track(event: string, props?: Record<string, unknown>): void;
  identify(id: string): void;
  reset(): void;
  people: { set(traits: Record<string, unknown>): void };
}

declare global {
  interface Window {
    mixpanel?: MixpanelLike;
  }
}

export function createMixpanel(token: string): AnalyticsAdapter {
  return {
    name: "mixpanel",
    async init() {
      await loadScript("https://cdn.mxpnl.com/libs/mixpanel-2-latest.min.js");
      window.mixpanel?.init(token, { track_pageview: false, persistence: "localStorage" });
    },
    track(event, props) {
      window.mixpanel?.track(event, props);
    },
    page(path, props) {
      window.mixpanel?.track("page_view", { path, ...props });
    },
    identify(userId, traits) {
      window.mixpanel?.identify(userId);
      if (traits) window.mixpanel?.people.set(traits);
    },
    reset() {
      window.mixpanel?.reset();
    },
  };
}
