import { cn } from "@/lib/utils";

/**
 * 랜딩의 장면 머리 (docs/25 §5 "한 장의 긴 영수증이 출력되는 이야기"): 영수증의 한 줄처럼 "01 ─ ─ ─ 과거 × 현재".
 * 장면이 바뀔 때마다 같은 모양이 찍혀서, 스크롤이 영수증을 따라 내려가는 것처럼 읽힌다.
 */
export function ChapterMark({ n, label, tone = "ink", className }: { n: string; label: string; tone?: "ink" | "light"; className?: string }) {
  return (
    <p className={cn("tabular flex items-center gap-3 text-body-sm font-extrabold tracking-[0.04em]", tone === "light" ? "text-white/70" : "text-ink-2", className)}>
      <span>{n}</span>
      <span aria-hidden className={cn("h-0 flex-1 border-t-[1.5px] border-dashed", tone === "light" ? "border-white/25" : "border-ink/20")} />
      <span>{label}</span>
    </p>
  );
}

/** 사진 출처: 한국관광공사 사진은 출처를 단다 (공공누리 조건) */
export function PhotoCredit({ place, className }: { place: string; className?: string }) {
  return <span className={cn("text-caption font-medium text-muted-foreground", className)}>사진 ©한국관광공사 · {place}</span>;
}
