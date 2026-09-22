"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Send, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface ComposerProps {
  streaming: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
}

const MAX_LENGTH = 500;

export function Composer({ streaming, onSend, onStop }: ComposerProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // 내용에 맞춰 높이를 늘린다 (최대 5줄쯤)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [value]);

  // 답변이 끝나면 다시 입력창으로
  useEffect(() => {
    if (!streaming) ref.current?.focus({ preventScroll: true });
  }, [streaming]);

  const submit = () => {
    const text = value.trim();
    if (!text || streaming) return;
    onSend(text);
    setValue("");
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter 는 글자 확정이지 전송이 아니다
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={onSubmit} className="grid gap-1.5">
      <div className="flex items-end gap-2 rounded-[22px] border border-input bg-white p-2 pl-4 shadow-card focus-within:border-blue focus-within:ring-[3px] focus-within:ring-blue/25">
        <label htmlFor="chat-input" className="sr-only">
          짠이에게 보낼 메시지
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={1}
          value={value}
          maxLength={MAX_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={streaming}
          placeholder={streaming ? "짠이가 답하는 중이에요…" : "어디서, 몇 명이, 얼마로 놀 건가요?"}
          aria-describedby="chat-input-hint"
          className="max-h-[140px] min-h-10 flex-1 resize-none bg-transparent py-2 text-body text-ink outline-none placeholder:text-muted-foreground disabled:opacity-60"
        />
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="답변 멈추기"
            className="grid size-11 shrink-0 place-items-center rounded-2xl bg-ink text-white transition-transform hover:scale-105"
          >
            <Square aria-hidden className="size-4 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!value.trim()}
            aria-label="보내기"
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-2xl text-white transition-[transform,opacity]",
              "bg-blue-deep hover:brightness-110 disabled:opacity-40",
            )}
          >
            <Send aria-hidden className="size-[18px]" />
          </button>
        )}
      </div>
      <p id="chat-input-hint" className="px-2 text-caption text-muted-foreground">
        Enter 로 보내고, Shift + Enter 로 줄을 바꿔요. 짠이는 등록된 장소 안에서만 추천해요.
      </p>
    </form>
  );
}
