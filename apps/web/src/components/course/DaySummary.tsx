"use client";

import { Money } from "@/components/brand/Money";
import { Jjani } from "@/components/mascot/Jjani";
import type { CourseTotals, Transport } from "@/lib/api/types";
import { distance, minutes, transportLabel, won } from "@/lib/format";
import type { JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

interface DaySummaryProps {
  totals: CourseTotals;
  budget: number;
  partySize: number;
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
  /** 장소 수 */
  stops: number;
  /** 내 코스(고칠 수 있음)면 "초안" 문구, 친구 코스면 API 요약 */
  editable?: boolean;
}

/**
 * 결과 화면의 첫 화면 (docs/31 §11 · docs/33 §5): "그래서 오늘 어디 가면 되는데?"의 답을 3초 안에.
 * 남은 돈(가장 큰 숫자) · 예산과 쓴 돈 → 짠이의 한 줄 → 소요 · 이동 한 줄. 바로 아래가 첫 장소다 —
 * 경로 그림은 두지 않는다(일정이 하루의 흐름, 지도가 경로). 합계 · 남은 돈은 API 값 하나만 쓴다(영수증 · 짠이의 말과 같은 숫자).
 */
export function DaySummary({ totals, budget, partySize, transport, travelMin, distanceM, mood, line, summary, bubbleKey, stops, editable = true }: DaySummaryProps) {
  const over = totals.budget_left < 0;
  // docs/49: 많이 남았으면 "남았어요"로 끝내지 않고 왜 남았는지 말한다. 조금 남은 것은 일부러 둔 여유다
  const leftover = totals.leftover;
  const leftLine =
    totals.budget_left <= 0
      ? "짠! 예산에 딱 맞췄어요."
      : leftover && leftover.band !== "buffer" && leftover.text
        ? leftover.text
        : `짠! 예산 안에 맞췄어요. 여유 ${won(totals.budget_left)}은 남겨 뒀어요.`;
  return (
    <section aria-label="오늘의 요약" className="grid gap-3 sm:gap-4">
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

      {/* 한 줄 숫자: 총액 · 남음 · 이동 · 몇 곳 · 전체 시간 */}
      <p className="tabular text-body-sm font-semibold text-ink-2">
        총 {won(totals.price)} · <span className={over ? "text-pink-deep" : "text-gold-ink"}>{over ? `${won(-totals.budget_left)} 초과` : `${won(totals.budget_left)} 남음`}</span> · {transportLabel(transport)} {minutes(travelMin)} · {stops}곳 · 총 {minutes(totals.duration_min)}
        <span className="sr-only"> · 이동 거리 {distance(distanceM)}</span>
      </p>

      {/* 짠이는 여기서 한 번: 상태 한 줄 + 이 코스는 정답이 아니라 초안이라는 한 줄 (docs/42) */}
      <div key={bubbleKey} className="flex items-center gap-3">
        <Jjani mood={mood} size={44} className="shrink-0" />
        <div className="min-w-0">
          <p className="text-body font-bold text-ink">{line ?? leftLine}</p>
          <p className="text-body-sm text-ink-2">{editable ? "짠이가 먼저 예산 안에서 짜 봤어요. 마음에 안 드는 곳은 바꿔도 돼요 — 남은 돈은 바로 다시 계산할게요." : summary}</p>
        </div>
      </div>
    </section>
  );
}
