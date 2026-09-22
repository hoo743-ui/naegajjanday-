"use client";

import Link from "next/link";
import { RotateCw } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Jjani } from "@/components/mascot/Jjani";
import { Button } from "@/components/ui/button";
import { mascotCopyForError, type JjaniMood } from "@/lib/mascot-copy";
import { ChatCourseCard } from "./ChatCourseCard";
import type { AssistantMessage, ChatMessage } from "./useChat";

/** 도구 이름 → 진행 문구. 모르는 도구는 일반 문구로. */
const TOOL_STATUS: Record<string, string> = {
  generate_course: "코스 짜는 중…",
  search_places: "장소 찾는 중…",
  swap_stop: "한 곳만 바꾸는 중…",
  get_events: "근처 이벤트 찾는 중…",
};

function moodOf(message: AssistantMessage): JjaniMood {
  if (message.status === "error" && message.error) return mascotCopyForError(message.error).mood;
  if (message.status === "streaming") return "think";
  if (message.course) return "done";
  return "hi";
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1.5" role="status" aria-label="짠이가 답을 쓰는 중">
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-1.5 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: `${i * 140}ms` }} />
      ))}
    </span>
  );
}

function AssistantBubble({ message, onRetry, canRetry }: { message: AssistantMessage; onRetry: () => void; canRetry: boolean }) {
  const errorCopy = message.status === "error" && message.error ? mascotCopyForError(message.error) : null;
  const waiting = message.status === "streaming" && !message.content && !message.tool && !message.course;

  return (
    <div className="flex items-start gap-2.5">
      <Jjani mood={moodOf(message)} size={44} animated={message.status === "streaming"} decorative className="mt-0.5" />
      <div className="grid min-w-0 flex-1 justify-items-start gap-2">
        <span className="sr-only">짠이: </span>

        {message.content || waiting ? (
          <div className="max-w-full rounded-[20px] rounded-tl-md bg-white px-4 py-2.5 shadow-soft text-body font-medium whitespace-pre-wrap text-ink sm:max-w-[88%]">
            {message.content || <TypingDots />}
          </div>
        ) : null}

        {message.tool ? (
          <span role="status" className="inline-flex items-center gap-2 rounded-full bg-blue-soft px-3 py-1.5 text-body-sm font-semibold text-blue-deep">
            <span aria-hidden className="size-3 animate-spin rounded-full border-2 border-blue-deep border-t-transparent" />
            {TOOL_STATUS[message.tool] ?? "짠이가 알아보는 중…"}
          </span>
        ) : null}

        {message.course ? (
          <div className="w-full sm:max-w-[440px]">
            <ChatCourseCard course={message.course} />
          </div>
        ) : null}

        {message.status === "stopped" ? <span className="text-caption font-semibold text-muted-foreground">답변을 멈췄어요.</span> : null}

        {errorCopy ? (
          <div role="alert" className="max-w-full rounded-[20px] rounded-tl-md border border-pink/40 bg-pink-soft px-4 py-3 sm:max-w-[88%]">
            <b className="block text-body font-extrabold text-ink">{errorCopy.title}</b>
            <p className="mt-0.5 text-body-sm text-ink-2">{errorCopy.description}</p>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              {errorCopy.retry && canRetry ? (
                <Button type="button" variant="outline" size="sm" className="rounded-lg font-bold" onClick={onRetry}>
                  <RotateCw aria-hidden /> 다시 보내기
                </Button>
              ) : null}
              {errorCopy.action && errorCopy.code !== "BUDGET_TOO_LOW" ? (
                <Button asChild variant="outline" size="sm" className="rounded-lg font-bold">
                  <Link href={errorCopy.action.href}>{errorCopy.action.label}</Link>
                </Button>
              ) : null}
              <span className="text-caption text-muted-foreground">오류 코드 {errorCopy.code}</span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
  /** 마지막 메시지일 때만 재시도 버튼을 보여준다 */
  isLast: boolean;
  onRetry: () => void;
}

export function MessageBubble({ message, isLast, onRetry }: MessageBubbleProps) {
  const reduced = useReducedMotion();
  return (
    <motion.li
      initial={reduced ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}
      className="list-none"
    >
      {message.role === "user" ? (
        <div className="flex justify-end">
          <p className="max-w-[85%] rounded-[20px] rounded-br-md bg-[image:linear-gradient(120deg,#2F6BEA,#5B7FF5)] px-4 py-2.5 text-body font-medium whitespace-pre-wrap text-white">
            <span className="sr-only">나: </span>
            {message.content}
          </p>
        </div>
      ) : (
        <AssistantBubble message={message} onRetry={onRetry} canRetry={isLast} />
      )}
    </motion.li>
  );
}
