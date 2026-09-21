/**
 * NEXT_PUBLIC_API_MOCKING=enabled 일 때만: Node 런타임의 fetch 도 MSW 로 가로챈다.
 * (브라우저 쪽은 lib/api/mock-ready.ts 가 서비스 워커를 띄운다)
 */
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled") {
    const { server } = await import("./mocks/server");
    server.listen({ onUnhandledRequest: "bypass" });
    console.info("[MSW] server-side mocking enabled");
  }
}
