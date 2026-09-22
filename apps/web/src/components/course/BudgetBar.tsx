"use client";

import { Receipt } from "@/components/brand/Receipt";
import type { CourseTotals, Stop } from "@/lib/api/types";
import { distance, minutes, percent, roleLabel, transportLabel, won } from "@/lib/format";
import type { Transport } from "@/lib/api/types";

interface BudgetBarProps {
  totals: CourseTotals;
  budget: number;
  partySize: number;
  stops: Stop[];
  /** 영수증 머리: "홍대입구 · 데이트 · 2명" */
  heading: string;
  /** 이동: 영수증 아래에 한 줄로 — 예산 + 이동이 한 장의 "오늘의 하루"가 된다 */
  travel?: { mode: Transport; minutes: number; distanceM: number };
  className?: string;
}

/**
 * 코스의 합계 = 영수증 (docs/19). 이전에는 "총 예상 지출 + 진행 막대"였는데, 무엇에 얼마가 드는지는
 * 아래 카드를 하나씩 내려가며 더해 봐야 알 수 있었다. 영수증은 품목 · 합계 · 남은 돈을 한 장에 보여 준다.
 */
export function BudgetBar({ totals, budget, partySize, stops, heading, travel, className }: BudgetBarProps) {
  const over = totals.budget_left < 0;
  const ratio = budget > 0 ? totals.price / budget : 0;
  return (
    <section aria-label="예산 사용 현황" className={className}>
      <p className="sr-only">
        예산 {won(budget)} 중 {won(totals.price)} 사용, {over ? `${won(-totals.budget_left)} 초과` : `${won(totals.budget_left)} 남음`}
      </p>
      <Receipt
        heading={heading}
        items={stops.map((s) => {
          const free = s.place.is_free === true || (s.est_price === 0 && s.place.price_per_person === 0);
          return {
            label: roleLabel(s.role),
            name: s.place.name,
            price: s.est_price,
            estimated: s.place.price_is_estimated === true && s.est_price > 0,
            unknown: !free && s.est_price === 0,
          };
        })}
        // 합계 · 남은 돈은 API 가 계산한 값 하나만 쓴다 (짠이의 한마디 · 영수증 · 정산 문구가 같은 숫자)
        totals={{ price: totals.price, left: totals.budget_left }}
        budget={budget}

        footer={
          <>
            <span className="tabular font-bold">
              예산의 {percent(ratio)} 사용{partySize > 1 ? ` · 1인 ${won(totals.price_per_person)}` : ""}
            </span>
            {travel && travel.minutes > 0 ? (
              <span className="tabular mt-0.5 block">
                {transportLabel(travel.mode)} 이동 {minutes(travel.minutes)} · {distance(travel.distanceM)}
              </span>
            ) : null}
            {over ? <span className="mt-1 block font-bold text-pink-deep">한 곳만 “더 저렴하게”로 바꾸면 예산 안으로 들어와요.</span> : null}
          </>
        }
      />
    </section>
  );
}
