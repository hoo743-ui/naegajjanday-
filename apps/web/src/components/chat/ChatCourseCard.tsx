"use client";

import Link from "next/link";
import { ArrowRight, Footprints } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Course } from "@/lib/api/types";
import { minutes, roleLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 챗봇의 `course` 이벤트 payload 를 대화 안에 카드로 보여준다 */
export function ChatCourseCard({ course }: { course: Course }) {
  const { totals } = course;
  const over = totals.budget_left < 0;
  const used = Math.min(100, Math.max(0, Math.round(totals.budget_utilization * 100)));

  return (
    <article aria-label={`${course.label}: ${course.summary}`} className="bg-grad-soft w-full rounded-[22px] p-3.5 sm:p-4">
      <header className="mb-3 px-1">
        <span className="text-xs font-extrabold text-blue-deep">{course.label}</span>
        <h3 className="text-base leading-snug font-extrabold tracking-tight text-ink">{course.summary}</h3>
      </header>

      <ol className="grid gap-2">
        {course.stops.map((stop) => (
          <li key={stop.position} className="flex items-center gap-3 rounded-2xl border border-white/90 bg-white/75 px-3.5 py-2.5">
            <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-blue-deep text-[13px] font-extrabold text-white">
              {stop.position}
            </span>
            <span className="min-w-0 flex-1">
              <small className="block text-[11.5px] font-extrabold text-blue-deep">{roleLabel(stop.role)}</small>
              <b className="block truncate text-[15px] font-extrabold tracking-tight text-ink">{stop.place.name}</b>
            </span>
            <b className="tabular shrink-0 text-[15px] font-extrabold text-ink">{stop.est_price === 0 ? "무료" : won(stop.est_price)}</b>
          </li>
        ))}
      </ol>

      <div className="mt-3 rounded-2xl bg-white p-3.5 shadow-soft">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-[13px] font-extrabold text-muted-foreground">총 예상 지출</span>
          <b className="tabular text-xl font-extrabold tracking-tight text-ink">{won(totals.price)}</b>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#EEF2F8]" aria-hidden>
          <div className={cn("h-full rounded-full", over ? "bg-pink-deep" : "bg-grad")} style={{ width: `${used}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[12.5px] font-extrabold">
          <span className="flex items-center gap-1 text-muted-foreground">
            <Footprints aria-hidden className="size-3.5" />
            이동 {minutes(totals.travel_min)}
          </span>
          <span className={cn("tabular", over ? "text-pink-deep" : "text-blue-deep")}>
            {over ? `${won(-totals.budget_left)} 넘어요` : `${won(totals.budget_left)} 남음`}
          </span>
        </div>
      </div>

      <Button asChild variant="brand" size="md" className="mt-3 w-full">
        <Link href={`/course/${encodeURIComponent(course.id)}`}>
          코스 자세히 보기 <ArrowRight aria-hidden />
        </Link>
      </Button>
    </article>
  );
}
