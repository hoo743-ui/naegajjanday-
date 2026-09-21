import { refreshAccessToken } from "@/lib/auth/token";
import { mockReady } from "./mock-ready";
import { ApiError, authHeaders, buildUrl, parseErrorResponse } from "./client";

export interface SseMessage {
  event: string;
  data: string;
  id?: string;
}

export interface SseOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  onMessage: (message: SseMessage) => void;
}

/**
 * fetch 기반 SSE 리더.
 * EventSource 를 쓰지 않는 이유: POST 본문과 Authorization 헤더를 실을 수 없기 때문.
 * 스트림이 정상 종료되면 resolve, 연결 실패·비정상 응답이면 ApiError 로 reject 한다.
 */
export async function streamSse(path: string, { method = "GET", body, signal, onMessage }: SseOptions): Promise<void> {
  // 헤더는 매번 새로 만든다 — 재시도 때는 갱신된 access token 이 실려야 한다
  const open = () =>
    fetch(buildUrl(path), {
      method,
      credentials: "include",
      signal,
      headers: {
        Accept: "text/event-stream",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...authHeaders(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  let res: Response;
  try {
    await mockReady();
    res = await open();
    // client.ts 와 같은 규칙: access token(15분)이 만료됐으면 refresh 를 한 번만 하고 다시 연다
    if (res.status === 401 && typeof window !== "undefined") {
      const token = await refreshAccessToken();
      if (token) res = await open();
    }
  } catch (error) {
    if (signal?.aborted) return;
    throw ApiError.from(error);
  }
  if (!res.ok) throw await parseErrorResponse(res);
  if (!res.body) throw new ApiError({ code: "NETWORK_ERROR", status: 0, title: "스트림을 열지 못했어요" });

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const message = parseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (message) onMessage(message);
        boundary = buffer.indexOf("\n\n");
      }
    }
    const tail = parseBlock(buffer);
    if (tail) onMessage(tail);
  } catch (error) {
    if (signal?.aborted) return;
    throw ApiError.from(error);
  } finally {
    reader.releaseLock();
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  return data.length === 0 ? null : { event, data: data.join("\n"), id };
}

export function safeJson<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}
