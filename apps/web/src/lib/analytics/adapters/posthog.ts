import type { AnalyticsAdapter } from "../events";

/**
 * SDK 패키지 의존 없이 PostHog capture API 로 직접 보낸다 (번들 0KB).
 * feature flag·세션 리플레이가 필요해지면 posthog-js 로 교체하되 이 어댑터 인터페이스는 유지한다.
 */
export function createPosthog(apiKey: string, host = "https://us.i.posthog.com"): AnalyticsAdapter {
  const endpoint = `${host.replace(/\/$/, "")}/capture/`;
  const STORAGE_KEY = "njd_ph_id";
  let distinctId = "";

  const send = (event: string, properties: Record<string, unknown>) => {
    const payload = JSON.stringify({
      api_key: apiKey,
      event,
      distinct_id: distinctId,
      properties: { $current_url: window.location.href, ...properties },
      timestamp: new Date().toISOString(),
    });
    const beaconed = navigator.sendBeacon?.(endpoint, new Blob([payload], { type: "application/json" }));
    if (!beaconed) {
      void fetch(endpoint, {
        method: "POST",
        body: payload,
        headers: { "Content-Type": "application/json" },
        keepalive: true,
      }).catch(() => undefined);
    }
  };

  const persist = (id: string) => {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // 시크릿 모드 등: 세션 동안만 유지
    }
  };

  return {
    name: "posthog",
    init() {
      try {
        distinctId = localStorage.getItem(STORAGE_KEY) ?? crypto.randomUUID();
      } catch {
        distinctId = crypto.randomUUID();
      }
      persist(distinctId);
    },
    track: (event, props) => send(event, props),
    page: (path, props) => send("$pageview", { $pathname: path, ...props }),
    identify(userId, traits) {
      const anon = distinctId;
      distinctId = userId;
      send("$identify", { $anon_distinct_id: anon, $set: traits ?? {} });
    },
    reset() {
      distinctId = crypto.randomUUID();
      persist(distinctId);
    },
  };
}
