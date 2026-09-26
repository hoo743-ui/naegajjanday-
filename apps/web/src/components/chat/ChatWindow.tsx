"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, RotateCcw } from "lucide-react";
import { JjaniBubble } from "@/components/mascot/JjaniBubble";
import { useFeatures } from "@/lib/api/hooks";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import { useChat } from "./useChat";

/** 첫 화면의 예시 문장 — 데이터가 아니라 "이렇게 말해 보세요"라는 UI 안내 문구다. */
const SUGGESTIONS = [
  "성수에서 3만원으로 혼밥하고 전시 볼래",
  "홍대에서 둘이 4만원으로 데이트 코스 짜줘",
  "강남역 근처에서 친구 4명이 10만원으로 놀고 싶어",
];

export function ChatWindow() {
  const { messages, streaming, send, retry, stop, reset } = useChat();
  const features = useFeatures();
  const router = useRouter();
  const chatOn = features.data?.chat === true;
  const settledOff = features.isError || (features.data !== undefined && !chatOn);
  const endRef = useRef<HTMLDivElement>(null);
  const empty = messages.length === 0;

  useEffect(() => {
    if (settledOff) router.replace("/home");
  }, [settledOff, router]);

  // 새 토큰이 올 때마다 맨 아래로. 사용자가 위로 올려 읽는 중이면 방해하지 않는다.
  useEffect(() => {
    const el = endRef.current;
    if (!el) return;
    const nearBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 240;
    if (nearBottom || messages[messages.length - 1]?.role === "user") el.scrollIntoView({ block: "end" });
  }, [messages]);

  // 대화 기능이 켜졌다고 확인되기 전에는 대화 화면을 그리지 않는다. 꺼져 있거나(LLM 미설정) 확인에 실패하면
  // 홈으로 돌려보낸다 — 주소로 바로 들어와도 멈춘 채팅 화면을 보지 않게(2026-09-26 창업자 제보).
  if (!chatOn) {
    return <div aria-busy="true" className="min-h-[calc(100dvh-68px)]" />;
  }

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-68px)] w-full max-w-3xl flex-col px-4 sm:px-6">
      <div className="flex items-center justify-between pt-6 pb-2">
        <h1 className="text-h1 font-bold">짠이와 대화</h1>
        {!empty ? (
          <button type="button" onClick={reset} className="inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-body-sm font-semibold text-ink-2 hover:bg-white">
            <RotateCcw aria-hidden className="size-4" /> 새 대화
          </button>
        ) : null}
      </div>

      <div className="flex-1 pb-6">
        {empty ? (
          <div className="grid gap-6 pt-6 sm:pt-12">
            <JjaniBubble mood="hi" title="오늘 어디 갈지 고민되시나요?" tone="white" size={72}>
              지역이랑 예산, 인원만 말해 주세요. 장소는 제가 지어내지 않고, 등록된 곳 중에서만 골라 드려요.
            </JjaniBubble>
            <div>
              <p className="mb-2.5 text-body-sm font-semibold text-ink-2">이렇게 말해 보세요</p>
              <ul className="grid border-t border-ink/10">
                {SUGGESTIONS.map((text) => (
                  <li key={text} className="border-b border-ink/10">
                    <button
                      type="button"
                      onClick={() => send(text, true)}
                      className="group flex w-full items-center justify-between gap-3 py-4 text-left text-body font-semibold text-ink hover:text-blue-deep"
                    >
                      “{text}”
                      <ArrowRight aria-hidden className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-blue-deep" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <ol role="log" aria-live="polite" aria-relevant="additions" aria-label="대화 내용" className="grid gap-4 pt-2">
            {messages.map((message, i) => (
              <MessageBubble key={message.id} message={message} isLast={i === messages.length - 1} onRetry={retry} />
            ))}
          </ol>
        )}
        <div ref={endRef} className="h-px scroll-mb-40" />
      </div>

      <div className="sticky bottom-0 -mx-4 bg-[linear-gradient(180deg,transparent,var(--soft)_28%)] px-4 pt-6 pb-[max(14px,env(safe-area-inset-bottom))] sm:-mx-6 sm:px-6">
        <Composer streaming={streaming} onSend={(content) => send(content)} onStop={stop} />
        <p className="mt-2 text-center text-caption text-muted-foreground">짠이는 가격과 영업시간을 틀릴 수 있어요. 가기 전에 한 번 확인해 주세요.</p>
      </div>
    </div>
  );
}
