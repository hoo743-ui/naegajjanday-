"use client";

import { ArrowRight, Compass } from "lucide-react";
import type { Familiarity } from "@/lib/api/types";

interface FamiliarityLineProps {
  familiarity: Familiarity;
  /** history = 지난 코스로 알아챘다 · asked = 직접 골랐다 */
  source?: "asked" | "history" | null;
  busy?: boolean;
  onChange: (next: Familiarity) => void;
}

/**
 * 처음 오는 사람 · 자주 오는 사람 (docs/59 #1). 위저드에 질문을 더하지 않고, 결과 화면에 한 줄만.
 * 처음(기본): "자주 오는 동네예요 → 안 가 본 곳으로 다시 짜기" · 자주: 왜 이렇게 짰는지 + 대표 코스로 돌아가는 길.
 */
export function FamiliarityLine({ familiarity, source, busy, onChange }: FamiliarityLineProps) {
  if (familiarity === "regular") {
    return (
      <p role="note" className="flex flex-wrap items-center gap-x-1 border-l-2 border-tomato pl-3 text-body-sm font-semibold text-ink-2">
        <span className="py-1">{source === "history" ? "자주 오신 동네라 안 가 본 곳 위주로 짰어요" : "안 가 본 곳 위주로 짰어요"}</span>
        <button type="button" onClick={() => onChange("first")} disabled={busy} className="-ml-1 inline-flex min-h-11 items-center rounded-lg px-2 font-bold text-blue-deep hover:bg-blue-soft disabled:opacity-50">
          처음처럼 대표 코스로
        </button>
      </p>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onChange("regular")}
      disabled={busy}
      // 좁은 화면에서는 "안 가 본 곳으로 다시 짜기"가 다음 줄로 (가로로 넘치지 않게)
      className="-ml-2 flex min-h-11 max-w-full flex-wrap items-center gap-x-1.5 justify-self-start rounded-lg px-2 py-1 text-left text-body-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink disabled:opacity-50"
    >
      <Compass aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      자주 오는 동네예요
      <ArrowRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="font-bold text-blue-deep">안 가 본 곳으로 다시 짜기</span>
    </button>
  );
}
