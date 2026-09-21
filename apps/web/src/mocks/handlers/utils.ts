import { HttpResponse, delay } from "msw";
import type { ProblemDetails } from "@/lib/api/types";
import { MockProblem } from "../fixtures/course-engine";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1").replace(/\/$/, "");

/** 핸들러 경로 → 절대 URL. 예: u("/meta/regions") */
export const u = (path: string) => `${API_URL}${path}`;

export function problem(status: number, code: string, title: string, detail?: string, meta?: Record<string, unknown>) {
  const body: ProblemDetails = {
    type: `https://api.naegajjanday.com/errors/${code.toLowerCase().replace(/_/g, "-")}`,
    title,
    status,
    code,
    detail,
    meta,
    trace_id: `mock-${Date.now().toString(36)}`,
  };
  return HttpResponse.json(body, { status, headers: { "Content-Type": "application/problem+json" } });
}

/** MockProblem 을 problem+json 응답으로 바꾼다 */
export function guard<T>(fn: () => T) {
  try {
    return HttpResponse.json(fn() as Record<string, unknown>);
  } catch (error) {
    if (error instanceof MockProblem) return problem(error.status, error.code, error.message, error.detail, error.meta);
    throw error;
  }
}

/** 실제 네트워크처럼 보이게 하는 지연. 서버(node)·테스트에서는 생략. */
export const latency = (ms = 250) => (typeof window === "undefined" ? Promise.resolve() : delay(ms));

export function paginate<T>(items: T[], url: URL, fallbackLimit = 20): { items: T[]; next_cursor: string | null } {
  const limit = Number(url.searchParams.get("limit")) || fallbackLimit;
  const offset = Number(url.searchParams.get("cursor")) || 0;
  const slice = items.slice(offset, offset + limit);
  return { items: slice, next_cursor: offset + limit < items.length ? String(offset + limit) : null };
}

/** text/event-stream 응답. frames 를 gap ms 간격으로 흘려보낸다. */
export function sse(frames: { event: string; data: unknown }[], gap = 45) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(`event: ${frame.event}\ndata: ${JSON.stringify(frame.data)}\n\n`));
        await new Promise((resolve) => setTimeout(resolve, gap));
      }
      controller.close();
    },
  });
  return new HttpResponse(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" },
  });
}

/** 문장을 토큰처럼 잘라 SSE 프레임으로 */
export function tokenFrames(text: string): { event: string; data: unknown }[] {
  return (text.match(/\S+\s*/g) ?? []).map((chunk) => ({ event: "token", data: { text: chunk } }));
}
