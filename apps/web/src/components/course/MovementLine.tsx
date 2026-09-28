"use client";

import type { Movement } from "@/lib/api/types";

interface MovementLineProps {
  movement: Movement;
  /** 기준점 이름 (역 · 동네). movement_anchor.label, 없으면 동네 이름 */
  anchorLabel: string;
  /** 기준점에서 몇 m 안에서 짰는지. 없으면 모드의 기본값(800m · 2km) */
  radiusM?: number | null;
  /** onward 일 때 넘어간 곳 */
  onwardLabel?: string | null;
  busy?: boolean;
  onChange: (next: Movement) => void;
}

const DEFAULT_RADIUS: Record<Movement, number> = { inside: 800, around: 2000, onward: 2000 };

const radiusText = (m: number) => (m >= 1000 ? `${Number((m / 1000).toFixed(1))}km` : `${Math.round(m)}m`);

/**
 * 얼마나 움직일지 (docs/65 §2): 위저드에 질문을 더하지 않고(docs/61) 결과 화면에 한 줄만.
 * 역 안에서(M1) · 역 주변(M2, 기본) · 다른 동네로 한 번(M3). 모드는 약속이라 지금 범위를 숫자로 말한다.
 */
export function MovementLine({ movement, anchorLabel, radiusM, onwardLabel, busy, onChange }: MovementLineProps) {
  const radius = radiusText(radiusM ?? DEFAULT_RADIUS[movement]);
  const text =
    movement === "inside"
      ? `${anchorLabel} ${radius} 안, 걸어서만`
      : movement === "onward"
        ? `${anchorLabel} → ${onwardLabel || "다른 동네"} 한 번 이동`
        : `${anchorLabel} 주변 ${radius} 안에서 짰어요`;
  const actions: { to: Movement; label: string }[] =
    movement === "inside"
      ? [{ to: "around", label: "조금 더 돌아보기" }]
      : movement === "onward"
        ? [{ to: "around", label: "한 동네만" }]
        : [
            { to: "inside", label: "역 근처에서만" },
            { to: "onward", label: "다른 동네로" },
          ];
  return (
    // 좁은 화면에서는 버튼이 다음 줄로 (가로로 넘치지 않게)
    <p role="note" className="flex min-w-0 flex-wrap items-center gap-x-1 text-body-sm font-semibold text-ink-2">
      <span className="min-w-0 py-1 break-keep">{text}</span>
      <span aria-hidden className="text-muted-foreground">·</span>
      {actions.map((a) => (
        <button
          key={a.to}
          type="button"
          onClick={() => onChange(a.to)}
          disabled={busy}
          className="inline-flex min-h-11 items-center rounded-lg px-2 font-bold text-blue-deep hover:bg-blue-soft disabled:opacity-50"
        >
          {a.label}
        </button>
      ))}
    </p>
  );
}
