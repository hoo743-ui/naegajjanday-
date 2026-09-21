/**
 * 통합 분석 레이어. 화면 코드는 track()/page() 만 알면 되고, 어떤 도구로 나가는지는 환경변수가 정한다.
 * 어댑터는 해당 NEXT_PUBLIC_* 키가 있을 때만 동적 import 된다 → 키가 없으면 SDK 코드도 내려가지 않는다.
 */
import type { AnalyticsAdapter, AnalyticsEventName, AnalyticsEvents } from "./events";

const GA4_ID = process.env.NEXT_PUBLIC_GA4_ID;
const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST;
const MIXPANEL_TOKEN = process.env.NEXT_PUBLIC_MIXPANEL_TOKEN;

const adapters: AnalyticsAdapter[] = [];
const queue: Array<(adapter: AnalyticsAdapter) => void> = [];
let started = false;
let ready = false;

export async function initAnalytics(): Promise<void> {
  if (started || typeof window === "undefined") return;
  started = true;

  const loaders: Promise<AnalyticsAdapter>[] = [];
  if (GA4_ID) loaders.push(import("./adapters/ga4").then((m) => m.createGa4(GA4_ID)));
  if (POSTHOG_KEY) loaders.push(import("./adapters/posthog").then((m) => m.createPosthog(POSTHOG_KEY, POSTHOG_HOST)));
  if (MIXPANEL_TOKEN) loaders.push(import("./adapters/mixpanel").then((m) => m.createMixpanel(MIXPANEL_TOKEN)));

  const settled = await Promise.allSettled(
    loaders.map(async (loader) => {
      const adapter = await loader;
      await adapter.init();
      return adapter;
    }),
  );
  for (const result of settled) if (result.status === "fulfilled") adapters.push(result.value);
  ready = true;
  for (const job of queue.splice(0)) run(job);
}

function run(job: (adapter: AnalyticsAdapter) => void) {
  for (const adapter of adapters) {
    try {
      job(adapter);
    } catch {
      // 분석 실패가 화면을 깨면 안 된다
    }
  }
}

function dispatch(job: (adapter: AnalyticsAdapter) => void) {
  if (typeof window === "undefined") return;
  if (!ready) {
    if (queue.length < 100) queue.push(job);
    return;
  }
  run(job);
}

export function track<E extends AnalyticsEventName>(event: E, props: AnalyticsEvents[E]): void {
  if (process.env.NODE_ENV === "development") console.debug("[analytics]", event, props);
  dispatch((a) => a.track(event, props as Record<string, unknown>));
}

export function page(path: string, props?: Record<string, unknown>): void {
  dispatch((a) => a.page(path, props));
}

export function identify(userId: string, traits?: Record<string, unknown>): void {
  dispatch((a) => a.identify?.(userId, traits));
}

export function resetAnalytics(): void {
  dispatch((a) => a.reset?.());
}

export type { AnalyticsEventName, AnalyticsEvents } from "./events";
