"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronDown, MapPinned } from "lucide-react";
import { cn } from "@/lib/utils";

interface MoreHereProps {
  /** 접혀 있을 때 보이는 한 문장 (동네 소개가 있으면 그것) */
  summary: string;
  children: ReactNode;
}

/**
 * "이 동네 더 보기" (docs/59 #3 · docs/46 §4 "한 문장 + 펼침"): 장소 목록과 영수증 뒤에 늘어서던 블록 열 개
 * (오늘의 이동 · 예산을 바꾸면? · 지나갈 길 · 이런 동네예요 · 남은 돈으로 · 짠이의 이야기 · 공연 · 축제 …)를 한 줄로 접는다.
 * 펼칠 때만 그려서, 접힌 동안에는 그 블록들의 조회도 하지 않는다.
 */
export function MoreHere({ summary, children }: MoreHereProps) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <section aria-label="이 동네 더 보기" className="grid gap-4">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-11 w-full min-w-0 items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3 text-left transition-colors hover:border-ink-2"
      >
        <MapPinned aria-hidden className="size-5 shrink-0 text-blue-deep" />
        <span className="min-w-0 flex-1">
          <b className="block text-body font-bold text-ink">이 동네 더 보기</b>
          {open ? null : <span className="line-clamp-2 text-body-sm text-ink-2">{summary}</span>}
        </span>
        <ChevronDown aria-hidden className={cn("size-5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={bodyId} className="grid min-w-0 gap-4">
          {children}
        </div>
      ) : null}
    </section>
  );
}
