/**
 * NEXT_PUBLIC_API_MOCKING=enabled 일 때만 MSW 워커를 띄운다.
 * 모든 브라우저 fetch 경로(client/sse/token)가 첫 요청 전에 이 promise 를 기다린다
 * → 워커가 뜨기 전에 나간 요청이 실제 네트워크로 새는 일을 막는다.
 * 비활성일 땐 즉시 resolve 되고, mocks 청크는 로드되지 않는다.
 */
let pending: Promise<void> | null = null;

export function mockReady(): Promise<void> {
  if (process.env.NEXT_PUBLIC_API_MOCKING !== "enabled" || typeof window === "undefined") {
    return Promise.resolve();
  }
  pending ??= import("@/mocks/browser")
    .then(({ startWorker }) => startWorker())
    .catch((error: unknown) => {
      console.error("[msw] 워커를 시작하지 못했어요. public/mockServiceWorker.js 가 있는지 확인하세요.", error);
    });
  return pending;
}
