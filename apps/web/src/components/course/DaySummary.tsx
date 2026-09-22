"use client";

import { DayRoute } from "@/components/brand/DayRoute";
import { Money } from "@/components/brand/Money";
import { Jjani } from "@/components/mascot/Jjani";
import type { CourseTotals, Stop, Transport } from "@/lib/api/types";
import { clock, distance, minutes, roleLabel, transportLabel, won } from "@/lib/format";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

interface DaySummaryProps {
  totals: CourseTotals;
  budget: number;
  partySize: number;
  stops: Stop[];
  transport: Transport;
  /** 실제 경로(docs/27)로 잰 이동. 없으면 엔진의 추정값 */
  travelMin: number;
  distanceM: number;
  mood: JjaniMood;
  /** 예산을 넘었을 때만 짠이가 먼저 말한다 ("괜찮아요, 조금만 더 맞춰 볼까요?") */
  line?: string;
  /** API 가 쓴 한 줄 요약: "둘이서 61,600원, 걸어서 19분이면 충분해요" */
  summary: string;
  bubbleKey: string;
}

/**
 * 결과 화면의 첫 화면 (docs/31 §11): "그래서 오늘 어디 가면 되는데?"의 답을 3초 안에.
 * 남은 돈(가장 큰 숫자) · 예산과 쓴 돈 → 오늘의 경로(시각 + 곳) → 전체 소요 · 이동. 상자가 아니라 종이 위의 서식이고,
 * 아래(일정)와는 구멍 줄로 나뉜다. 합계 · 남은 돈은 API 값 하나만 쓴다(영수증 · 짠이의 말과 같은 숫자).
 */
export function DaySummary({ totals, budget, partySize, stops, transport, travelMin, distanceM, mood, line, summary, bubbleKey }: DaySummaryProps) {
  const over = totals.budget_left < 0;
  return (
    <section aria-label="오늘의 요약" className="grid gap-5">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-6 gap-y-3">
        <div className="grid">
          <span className={cn("text-body-sm font-semibold", over ? "text-pink-deep" : "text-gold-ink")}>{over ? "예산 초과" : "남은 돈"}</span>
          <Money value={Math.abs(totals.budget_left)} className={cn("money text-price-lg", over ? "text-pink-deep" : "text-gold-ink")} />
        </div>
        <dl className="tabular grid gap-0.5 text-body-sm">
          <div className="flex items-baseline justify-between gap-6">
            <dt className="font-medium text-muted-foreground">예산</dt>
            <dd className="font-semibold text-ink-2">{won(budget)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-6">
            <dt className="font-medium text-muted-foreground">쓰는 돈</dt>
            <dd className="font-bold text-ink">{won(totals.price)}</dd>
          </div>
          {partySize > 1 ? (
            <div className="flex items-baseline justify-between gap-6">
              <dt className="font-medium text-muted-foreground">1인</dt>
              <dd className="font-semibold text-ink-2">{won(totals.price_per_person)}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      {/* 짠이는 여기서 한 번, 오늘의 하루를 한 문장으로 */}
      <p key={bubbleKey} className="flex items-center gap-3 text-body font-semibold text-ink-2">
        <Jjani mood={mood} size={40} className="shrink-0" />
        <span className="min-w-0">
          {line ? <b className="block font-bold text-ink">{line}</b> : null}
          {summary}
        </span>
      </p>

      {/* 오늘의 경로: 무엇을 하는지는 아래 일정이, 어디로 가는지는 지도가. 여기는 순서만 한눈에 */}
      <DayRoute
        dense
        className="sm:gap-x-0"
        stops={stops.map((s) => ({
          key: s.position,
          time: clock(s.arrive_at),
          label: roleLabel(s.role),
          name: <span className="line-clamp-2 break-all">{s.place.name}</span>,
        }))}
      />

      <dl className="tabular flex flex-wrap gap-x-5 gap-y-1 text-body-sm">
        {[
          { k: "총 소요", v: minutes(totals.duration_min) },
          { k: `${transportLabel(transport)} 이동`, v: minutes(travelMin) },
          { k: "이동 거리", v: distance(distanceM) },
        ].map((item) => (
          <div key={item.k} className="flex items-baseline gap-1.5">
            <dt className="text-muted-foreground">{item.k}</dt>
            <dd className="font-bold text-ink">{item.v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
