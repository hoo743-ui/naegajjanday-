import { cn } from "@/lib/utils";

/**
 * 랜딩의 장면 머리 = 경로 위의 한 정거장 (docs/31 §5). 위 장면에서 내려온 점선이 점 하나에 닿고, 그 옆에 이름.
 * 장면이 따로 떨어진 광고 블록이 아니라, 앞 장면에서 이어져 내려온 하루의 다음 곳처럼 읽힌다.
 * `n`(장면 순번)은 화면에 숫자로 찍지 않는다 — 순서는 선이 말한다.
 */
export function ChapterMark({ label, tone = "ink", className }: { n?: string; label: string; tone?: "ink" | "light"; className?: string }) {
  return (
    <p className={cn("relative flex items-center gap-3 pl-6 text-body-sm font-bold", tone === "light" ? "text-white/75" : "text-ink-2", className)}>
      <span aria-hidden className={cn("absolute bottom-1/2 left-[5px] h-[clamp(56px,7vw,96px)] border-l-2 border-dashed", tone === "light" ? "border-white/30" : "border-ink/20")} />
      <span aria-hidden className={cn("absolute top-1/2 left-0 size-3 -translate-y-1/2 rounded-full border-2", tone === "light" ? "border-white bg-navy" : "border-ink bg-paper")} />
      {label}
    </p>
  );
}

/** 사진 출처: 한국관광공사 사진은 출처를 단다 (공공누리 조건) */
export function PhotoCredit({ place, className }: { place: string; className?: string }) {
  return <span className={cn("text-caption font-medium text-muted-foreground", className)}>사진 ©한국관광공사 · {place}</span>;
}
