"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, Pin, RotateCw, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GenerateCourseRequest } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { BottomSheet } from "./BottomSheet";

export type Tweak = "value" | "near" | "indoor" | "quiet" | "photo" | "free";

/** 다시 짤 때의 바람 → 요청. "더 저렴하게" = wishes value, "덜 걷게" = move_style local (API 문서 기준) */
const TWEAKS: { key: Tweak; label: string }[] = [
  { key: "value", label: "더 저렴하게" },
  { key: "near", label: "덜 걷게" },
  { key: "indoor", label: "실내 위주" },
  { key: "quiet", label: "조용한 곳" },
  { key: "photo", label: "사진 좋은 곳" },
  { key: "free", label: "무료 더 넣기" },
];

export function tweaksToRequest(tweaks: Tweak[]): Pick<GenerateCourseRequest, "wishes" | "move_style"> {
  const wishes = tweaks.filter((t): t is Exclude<Tweak, "near"> => t !== "near");
  return {
    ...(wishes.length ? { wishes } : {}),
    ...(tweaks.includes("near") ? { move_style: "local" as const } : {}),
  };
}

interface RerollSheetProps {
  open: boolean;
  onClose: () => void;
  /** 이 코스에서 고정한 곳의 수 */
  pinned: number;
  changeHref?: string;
  onReroll: (tweaks: Tweak[]) => void;
}

/**
 * 다시 짜기 (docs/42): 고정한 곳은 두고 나머지를 새로. 원하면 방향을 한두 개 고른다(안 골라도 된다).
 * 조건(지역 · 예산 · 날짜) 자체를 바꾸고 싶으면 맨 아래 "조건 바꾸기"로 위저드에.
 */
export function RerollSheet({ open, onClose, pinned, changeHref, onReroll }: RerollSheetProps) {
  const [tweaks, setTweaks] = useState<Tweak[]>([]);
  const toggle = (t: Tweak) => setTweaks((now) => (now.includes(t) ? now.filter((x) => x !== t) : [...now, t]));

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title="다시 짜 볼까요?"
      description={pinned > 0 ? `고정한 ${pinned}곳은 그대로 두고 나머지를 바꿔요.` : "지금 코스의 장소는 빼고 새로 짜요."}
      footer={
        <div className="grid gap-2">
          <Button type="button" variant="brand" size="xl" className="w-full" onClick={() => onReroll(tweaks)}>
            <RotateCw aria-hidden /> {tweaks.length ? "이렇게 다시 짜기" : "그냥 다시 짜기"}
          </Button>
          {changeHref ? (
            <Link href={changeHref} className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl text-body-sm font-semibold text-ink-2 hover:bg-ink/[0.05] hover:text-ink">
              <SlidersHorizontal aria-hidden className="size-4" /> 조건 바꾸기 (지역 · 예산 · 날짜)
            </Link>
          ) : null}
        </div>
      }
    >
      <p className="mb-2 text-body-sm font-semibold text-ink-2">이번엔 이렇게 (골라도, 안 골라도 돼요)</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="다시 짤 방향">
        {TWEAKS.map((t) => {
          const on = tweaks.includes(t.key);
          return (
            <button
              key={t.key}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(t.key)}
              className={cn("inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-body-sm transition-colors", on ? "border-tomato bg-tomato font-bold text-white" : "border-ink/20 bg-white font-semibold text-ink-2 hover:border-tomato hover:bg-tomato-soft")}
            >
              {on ? <Check aria-hidden strokeWidth={3} className="size-4" /> : null}
              {t.label}
            </button>
          );
        })}
      </div>
      {pinned === 0 ? (
        <p className="mt-4 flex items-start gap-2 text-caption text-muted-foreground">
          <Pin aria-hidden className="mt-0.5 size-3.5 shrink-0" /> 마음에 드는 곳은 카드의 ⋯ 에서 &lsquo;이 장소 고정&rsquo;을 누르면 다시 짜도 남아요.
        </p>
      ) : null}
    </BottomSheet>
  );
}
