"use client";

import Link from "next/link";
import { ArrowRight, Footprints } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Course } from "@/lib/api/types";
import { minutes, roleLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * 챗봇의 `course` 이벤트 payload = 대화 안의 작은 영수증 (docs/25 — 코스는 어디서든 영수증 모양이다).
 * 품목(순번 · 역할 · 장소 · 가격) → 합계 → 남은 돈. 카드 안의 카드를 쌓지 않는다.
 */
export function ChatCourseCard({ course }: { course: Course }) {
  const { totals } = course;
  const over = totals.budget_left < 0;

  return (
    <article aria-label={`${course.label}: ${course.summary}`} className="w-full">
      <div className="receipt-wrap">
        <div className="receipt px-5 pt-6 pb-5">
          <p className="text-caption font-semibold text-blue-deep">{course.label}</p>
          <h3 className="mt-0.5 text-body font-bold text-ink">{course.summary}</h3>
          <hr className="receipt-rule my-3.5" />

          <ol className="grid gap-2">
            {course.stops.map((stop) => (
              <li key={stop.position} className="flex items-baseline gap-2 text-body-sm">
                <span className="tabular w-5 shrink-0 text-caption font-semibold text-muted-foreground">{String(stop.position).padStart(2, "0")}</span>
                <span className="min-w-0 shrink truncate font-semibold text-ink">
                  <span className="font-medium text-muted-foreground">{roleLabel(stop.role)}</span> {stop.place.name}
                </span>
                <span aria-hidden className="receipt-leader" />
                <span className="tabular shrink-0 font-bold text-ink">{stop.est_price === 0 ? "무료" : won(stop.est_price)}</span>
              </li>
            ))}
          </ol>

          <hr className="receipt-rule my-3.5" />
          <div className="flex items-baseline justify-between gap-3 text-body-sm">
            <span className="font-medium text-muted-foreground">합계</span>
            <b className="money text-body-lg text-ink">{won(totals.price)}</b>
          </div>
          <div className={cn("mt-3 flex items-baseline justify-between rounded-2xl px-4 py-3", over ? "bg-pink-soft text-pink-deep" : "bg-gold-soft text-gold-ink")}>
            <span className="text-body-sm font-semibold">{over ? "예산 초과" : "남은 돈"}</span>
            <b className="money text-price-sm">{won(Math.abs(totals.budget_left))}</b>
          </div>
          <p className="mt-2.5 flex items-center justify-center gap-1 text-caption text-muted-foreground">
            <Footprints aria-hidden className="size-3.5" />
            이동 {minutes(totals.travel_min)}
          </p>
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
