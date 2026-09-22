import { Check } from "lucide-react";

import type { ReasonCode } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * "왜 여기?"의 첫 줄: 엔진이 이 장소를 고른 이유를 말로 (docs/29 §15).
 * 점수 막대는 "얼마나"를, 이 목록은 "왜"를 말한다. 숫자나 확률은 보여 주지 않는다.
 */
const REASON_TEXT: Record<ReasonCode, string> = {
  PURPOSE_MATCH: "이번 목적에 잘 맞는 곳이에요",
  LOCAL_SIGNIFICANCE: "이 동네가 알려진 곳이에요",
  WORTH_THE_TRIP: "조금 더 가야 하지만, 그만큼 갈 만한 곳이라 넣었어요",
  UNIQUE_EXPERIENCE: "오늘 하루에 다른 결의 경험을 더해 줘요",
  USER_PREFERENCE: "고른 취향과 맞아요",
  HIGH_PLACE_QUALITY: "공공기관이 인정했거나 실제로 많이 찾는 곳이에요",
  BUDGET_FIT: "이 자리에 나눈 예산에 잘 맞아요",
  DIVERSITY: "앞뒤 장소와 겹치지 않아요",
  ROUTE_BALANCE: "앞 장소에서 무리 없이 이어져요",
};

export function reasonText(code: string): string | null {
  return (REASON_TEXT as Record<string, string>)[code] ?? null;
}

export function ReasonList({ codes, className }: { codes?: readonly string[] | null; className?: string }) {
  const lines = (codes ?? []).map(reasonText).filter((t): t is string => Boolean(t));
  if (lines.length === 0) return null;
  return (
    <ul className={cn("space-y-1.5", className)} aria-label="이 장소를 고른 이유">
      {lines.map((line) => (
        <li key={line} className="flex items-start gap-2 text-body-sm text-ink">
          <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-blue-deep" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}
