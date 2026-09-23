import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface BudgetChipProps {
  /** 큰 글자: "5만 원" */
  amount: string;
  /** 작은 보조 라벨: "무난하게" */
  hint?: string;
  selected: boolean;
  onSelect: () => void;
  disabled?: boolean;
  className?: string;
}

/**
 * 빠른 예산 선택 (히어로 · 위저드 공용). 지금 고른 예산이 1초 안에 보여야 한다 — 색만으로 말하지 않는다:
 * 고름 = 토마토 바탕 · 흰 글자 · 체크 · 굵게 / 안 고름 = 종이 바탕 · 얇은 잉크 테두리 · 보통 굵기.
 * 호버는 옅은 토마토, 키보드 초점은 전역 잉크 외곽선.
 */
export function BudgetChip({ amount, hint, selected, onSelect, disabled, className }: BudgetChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "tabular relative inline-flex min-h-12 items-center justify-center rounded-xl border px-3 py-1.5 text-center whitespace-nowrap transition-colors disabled:opacity-40",
        selected ? "border-tomato bg-tomato text-white shadow-[0_4px_12px_rgba(214,63,40,.25)]" : "border-ink/35 bg-paper text-ink hover:border-tomato hover:bg-tomato-soft",
        className,
      )}
    >
      {/* 체크는 모서리에: 글자 폭을 뺏지 않아 좁은 칸에서도 "무난하게"가 한 줄로 남는다 */}
      {selected ? (
        <span aria-hidden className="absolute -top-2 -right-2 grid size-5 place-items-center rounded-full border-2 border-paper bg-ink text-white">
          <Check strokeWidth={3.5} className="size-3" />
        </span>
      ) : null}
      <span className="grid leading-tight">
        <span className={cn("text-body-sm", selected ? "font-extrabold" : "font-semibold")}>{amount}</span>
        {hint ? <span className={cn("text-caption", selected ? "font-semibold text-white" : "font-medium text-muted-foreground")}>{hint}</span> : null}
      </span>
    </button>
  );
}
