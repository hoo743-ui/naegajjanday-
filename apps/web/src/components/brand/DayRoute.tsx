import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface DayRouteStop {
  key: string | number;
  /** "18:00" — 들르는 시각 */
  time?: string;
  /** 역할: 식사 · 카페 · 산책 … */
  label: string;
  name: ReactNode;
  /** 그 곳에서 쓰는 돈 (영수증 줄의 금액) */
  price?: ReactNode;
}

/**
 * 하루의 경로 (docs/31 §2 "경로"): 들르는 곳은 점, 이동은 점선. 넓은 화면에서는 왼쪽에서 오른쪽으로 흐르는 한 줄,
 * 좁은 화면에서는 위에서 아래로. 지도 기능이 아니라 "오늘은 이 순서로"라는 브랜드의 그림이다 —
 * 랜딩 히어로의 예시 하루와 결과 화면의 요약이 같은 모양을 쓴다.
 * 움직임(docs/32): 점이 차례로 놓이고 선이 그려진다 — 코스나 예산이 바뀌어 새로 그려질 때마다. 시간표는 globals.css `.day-route`.
 */
export function DayRoute({ stops, className, dense = false }: { stops: DayRouteStop[]; className?: string; dense?: boolean }) {
  return (
    <ol className={cn("day-route grid sm:auto-cols-fr sm:grid-flow-col", className)}>
      {stops.map((stop, i) => (
        <li key={stop.key} style={{ "--i": i } as CSSProperties} className={cn("relative grid content-start pl-8 sm:pl-0 sm:pr-4", i < stops.length - 1 && (dense ? "pb-3.5 sm:pb-0" : "pb-5 sm:pb-0"))}>
          {/* 다음 곳까지의 이동: 세로(모바일) · 가로(넓은 화면) 점선 */}
          {i < stops.length - 1 ? (
            <span aria-hidden className="route-seg absolute top-4 bottom-0 left-[5px] border-l-2 border-dashed border-ink/25 sm:top-[5px] sm:right-0 sm:bottom-auto sm:left-4 sm:border-t-2 sm:border-l-0" />
          ) : null}
          <span aria-hidden className={cn("route-dot absolute top-1.5 left-0 size-3 rounded-full border-2 border-ink bg-paper sm:static sm:mb-3", i === 0 && "is-start bg-ink")} />
          <span className="route-text grid">
          {stop.time ? <time className="tabular text-caption font-bold text-muted-foreground">{stop.time}</time> : null}
          <span className={cn("flex flex-wrap items-baseline gap-x-2 sm:grid", dense ? "gap-y-0" : "gap-y-0.5")}>
            <span className="text-caption font-semibold text-muted-foreground">{stop.label}</span>
            <span className={cn("font-semibold text-ink", dense ? "text-body-sm" : "text-body")}>{stop.name}</span>
          </span>
          {stop.price !== undefined ? <span className="tabular text-body-sm font-bold text-ink-2">{stop.price}</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
