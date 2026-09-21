"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { track } from "@/lib/analytics";
import { ApiError } from "@/lib/api/client";
import { useCreateChatSession } from "@/lib/api/hooks";
import { safeJson, streamSse } from "@/lib/api/sse";
import type { Course, ProblemDetails } from "@/lib/api/types";

export type AssistantStatus = "streaming" | "done" | "error" | "stopped";

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  status: AssistantStatus;
  /** 지금 실행 중인 도구 이름 (tool_call 이후 다음 이벤트가 올 때까지) */
  tool: string | null;
  course: Course | null;
  error: ApiError | null;
}

export type ChatMessage = UserMessage | AssistantMessage;

let seq = 0;
const nextId = () => `m${Date.now().toString(36)}_${++seq}`;

export function useChat() {
  const { mutateAsync: createSession } = useCreateChatSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const sessionId = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const lastContent = useRef<string | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const patch = useCallback((id: string, update: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id && m.role === "assistant" ? update(m) : m)));
  }, []);

  const run = useCallback(
    async (content: string, options: { appendUser: boolean; suggested: boolean }) => {
      const assistantId = nextId();
      lastContent.current = content;
      setStreaming(true);
      setMessages((prev) => [
        // 재시도일 땐 실패한 직전 답변을 걷어 낸다
        ...(options.appendUser ? prev : prev.filter((m, i) => !(i === prev.length - 1 && m.role === "assistant" && m.status === "error"))),
        ...(options.appendUser ? [{ id: nextId(), role: "user", content } satisfies UserMessage] : []),
        { id: assistantId, role: "assistant", content: "", status: "streaming", tool: null, course: null, error: null },
      ]);

      const controller = new AbortController();
      abort.current = controller;
      let failed = false;

      try {
        // 세션은 첫 메시지를 보낼 때 만든다
        sessionId.current ??= (await createSession()).id;
        const session = sessionId.current;
        track("chat_message_sent", { session_id: session, length: content.length, suggested: options.suggested });

        await streamSse(`/chat/sessions/${encodeURIComponent(session)}/messages`, {
          method: "POST",
          body: { content },
          signal: controller.signal,
          onMessage: ({ event, data }) => {
            switch (event) {
              case "token": {
                const text = safeJson<{ text?: string }>(data)?.text ?? "";
                if (text) patch(assistantId, (m) => ({ ...m, content: m.content + text, tool: null }));
                break;
              }
              case "tool_call": {
                const name = safeJson<{ name?: string }>(data)?.name ?? "tool";
                patch(assistantId, (m) => ({ ...m, tool: name }));
                break;
              }
              case "course": {
                const course = safeJson<Course>(data);
                if (course?.id && Array.isArray(course.stops)) {
                  patch(assistantId, (m) => ({ ...m, course, tool: null }));
                  track("chat_course_received", { session_id: session, course_id: course.id });
                }
                break;
              }
              case "error": {
                failed = true;
                const problem = safeJson<Partial<ProblemDetails>>(data);
                const error = new ApiError({
                  code: problem?.code ?? "INTERNAL_ERROR",
                  status: problem?.status ?? 500,
                  title: problem?.title ?? "문제가 생겼어요",
                  detail: problem?.detail,
                  meta: problem?.meta,
                  traceId: problem?.trace_id,
                });
                track("error_shown", { code: error.code, where: "chat" });
                patch(assistantId, (m) => ({ ...m, status: "error", tool: null, error }));
                break;
              }
              default:
                break; // done 은 스트림 종료로 처리
            }
          },
        });

        if (!failed) {
          patch(assistantId, (m) => ({ ...m, status: controller.signal.aborted ? "stopped" : "done", tool: null }));
        }
      } catch (cause) {
        if (controller.signal.aborted) {
          patch(assistantId, (m) => ({ ...m, status: "stopped", tool: null }));
        } else {
          const error = ApiError.from(cause);
          track("error_shown", { code: error.code, where: "chat" });
          patch(assistantId, (m) => ({ ...m, status: "error", tool: null, error }));
        }
      } finally {
        if (abort.current === controller) abort.current = null;
        setStreaming(false);
      }
    },
    [createSession, patch],
  );

  const send = useCallback(
    (content: string, suggested = false) => {
      const text = content.trim();
      if (!text || abort.current) return;
      void run(text, { appendUser: true, suggested });
    },
    [run],
  );

  const retry = useCallback(() => {
    if (!lastContent.current || abort.current) return;
    void run(lastContent.current, { appendUser: false, suggested: false });
  }, [run]);

  const stop = useCallback(() => abort.current?.abort(), []);

  const reset = useCallback(() => {
    abort.current?.abort();
    sessionId.current = null;
    lastContent.current = null;
    setMessages([]);
  }, []);

  return { messages, streaming, send, retry, stop, reset };
}
