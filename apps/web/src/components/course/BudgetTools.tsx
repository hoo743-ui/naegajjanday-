"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check, Copy, Minus, Plus } from "lucide-react";
import { track } from "@/lib/analytics";
import { useGenerateCourse } from "@/lib/api/hooks";
import type { Course, GenerateCourseRequest, Stop } from "@/lib/api/types";
import { roleLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";

interface BudgetToolsProps {
  /** 지금 코스를 만든 조건 그대로 (예산만 바꿔서 다시 보낸다) */
  baseRequest: GenerateCourseRequest;
  budget: number;
  partySize: number;
  stops: Stop[];
  total: number;
  /** 정산 문구 첫 줄: "9월 25일 (금) · 홍대입구" */
  heading: string;
  courseUrl: string;
}

/** 예산을 얼마나 흔들어 볼지: 20% 를 만 원 단위로, 최소 1만 원 */
const stepOf = (budget: number) => Math.max(10_000, Math.round((budget * 0.2) / 10_000) * 10_000);

/**
 * 영수증 아래의 두 가지 도구 — 둘 다 "예산이 코스를 설계한다"는 컨셉에서 나온다.
 *  1) 만약에: 예산을 조금 덜/더 쓰면 하루가 어떻게 달라지는지 그 자리에서 비교한다 (새 코스는 눌렀을 때만 연다).
 *  2) 정산: 영수증을 단톡방에 붙일 1/N 문구로 복사한다. 금액은 화면의 영수증과 같은 숫자다.
 */
export function BudgetTools({ baseRequest, budget, partySize, stops, total, heading, courseUrl }: BudgetToolsProps) {
  const whatIf = useGenerateCourse();
  const [tried, setTried] = useState<{ budget: number; course: Course } | null>(null);
  const [copied, setCopied] = useState(false);
  const step = stepOf(budget);

  const tryBudget = (next: number) => {
    setTried(null);
    track("budget_whatif_tried", { budget_total: next, from_budget: budget });
    whatIf.mutate(
      { ...baseRequest, budget_total: next, alternatives: 0 },
      { onSuccess: (res) => res.courses[0] && setTried({ budget: next, course: res.courses[0] }) },
    );
  };

  const copySettlement = async () => {
    const each = Math.ceil(total / Math.max(1, partySize) / 100) * 100;
    const lines = [
      `[내가짠데이] ${heading}`,
      ...stops.map((s) => `${s.position}. ${s.place.name} ${s.est_price > 0 ? won(s.est_price) : "무료"}`),
      `합계 ${won(total)}${partySize > 1 ? ` → ${partySize}명이면 1인 ${won(each)}` : ""}`,
      "※ 업종 평균가로 계산한 곳이 있어 실제와 다를 수 있어요.",
      courseUrl,
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      track("settlement_copied", { party_size: partySize, total });
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch {
      // 클립보드 권한이 없는 환경: 조용히 넘어간다
    }
  };

  const before = new Set(stops.map((s) => s.place.id));
  const added = tried?.course.stops.filter((s) => !before.has(s.place.id)) ?? [];

  return (
    <section aria-label="예산 도구" className="grid gap-3 rounded-card bg-white p-5 shadow-soft">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-[15px] font-extrabold text-ink">예산을 바꾸면?</h2>
        <button
          type="button"
          disabled={whatIf.isPending || budget - step < 10_000}
          onClick={() => tryBudget(budget - step)}
          className="tabular inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-[13.5px] font-bold text-ink-2 hover:border-blue-deep disabled:opacity-40"
        >
          <Minus aria-hidden className="size-3.5" /> {won(step)} 덜
        </button>
        <button
          type="button"
          disabled={whatIf.isPending}
          onClick={() => tryBudget(budget + step)}
          className="tabular inline-flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-[13.5px] font-bold text-ink-2 hover:border-blue-deep disabled:opacity-40"
        >
          <Plus aria-hidden className="size-3.5" /> {won(step)} 더
        </button>
      </div>

      <div aria-live="polite">
        {whatIf.isPending ? <p className="skeleton-shimmer h-16 rounded-2xl" aria-label="그 예산으로 짜 보는 중" /> : null}
        {whatIf.isError ? <p className="rounded-2xl bg-paper-2 text-ink-2 px-4 py-3 text-[13.5px] font-bold">{whatIf.error.detail ?? "그 예산으로는 코스를 짜지 못했어요."}</p> : null}
        {tried ? (
          <div className="grid gap-2 rounded-2xl bg-soft p-4">
            <p className="tabular text-[14px] font-extrabold text-ink">
              예산 {won(tried.budget)}이면 <span className="text-blue-deep">{tried.course.stops.length}곳</span>, 합계 <span className="text-gold-ink">{won(tried.course.totals.price)}</span>
              <span className="font-semibold text-ink-2"> (지금 {stops.length}곳 · {won(total)})</span>
            </p>
            <p className="text-[13px] leading-relaxed text-ink-2">{tried.course.stops.map((s) => `${roleLabel(s.role)} ${s.place.name}`).join(" → ")}</p>
            {added.length > 0 ? <p className="text-[12.5px] text-muted-foreground">달라지는 곳: {added.map((s) => s.place.name).join(", ")}</p> : null}
            <Link href={`/course/${encodeURIComponent(tried.course.id)}`} onClick={() => track("budget_whatif_opened", { course_id: tried.course.id, budget_total: tried.budget })} className="inline-flex items-center gap-1 text-[13.5px] font-extrabold text-blue-deep hover:underline">
              이 코스 열어 보기 <ArrowRight aria-hidden className="size-4" />
            </Link>
          </div>
        ) : null}
      </div>

      <button
        type="button"
        onClick={() => void copySettlement()}
        className={cn("inline-flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-[14.5px] font-bold", copied ? "border-blue-deep bg-blue-soft text-blue-deep" : "border-line text-ink hover:border-blue-deep")}
      >
        {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
        {copied ? "복사했어요. 단톡방에 붙여 넣으세요" : partySize > 1 ? `${partySize}명 정산 문구 복사` : "영수증 문구 복사"}
      </button>
    </section>
  );
}
