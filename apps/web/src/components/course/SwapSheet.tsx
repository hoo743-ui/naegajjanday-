"use client";

import { useEffect, useRef } from "react";
import { MapPin, TrendingDown } from "lucide-react";
import { PlacePlaceholder } from "@/components/brand/PlacePlaceholder";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useStopCandidates } from "@/lib/api/hooks";
import type { Stop, SwapStrategy } from "@/lib/api/types";
import { roleLabel, won } from "@/lib/format";
import { canOptimize } from "@/lib/photo-credit";
import Image from "next/image";
import { BottomSheet } from "./BottomSheet";

interface SwapSheetProps {
  open: boolean;
  onClose: () => void;
  courseId: string;
  stop: Stop;
  /** 후보에서 고른 곳으로 */
  onPick: (placeId: string) => void;
  /** 짠이에게 맡기기: 더 저렴하게 · 더 가까이 */
  onStrategy: (strategy: SwapStrategy) => void;
}

const delta = (n: number) => (n === 0 ? "같은 금액" : n < 0 ? `${won(-n)} 아껴요` : `${won(n)} 더`);

/**
 * 바꾸기 (docs/42): 이 자리만 바꾸고 나머지는 그대로 — 남은 돈은 서버가 바로 다시 계산한다.
 * 대신 갈 곳 2~3곳을 먼저(얼마가 달라지는지와 한 줄 이유), 그 아래 "짠이에게 맡기기" 두 가지.
 */
export function SwapSheet({ open, onClose, courseId, stop, onPick, onStrategy }: SwapSheetProps) {
  return (
    <BottomSheet open={open} onClose={onClose} title={`${roleLabel(stop.role)} 자리를 바꿔요`} description="한 곳만 바꿔도 남은 돈은 바로 다시 계산할게요.">
      <p className="mb-2 text-body-sm font-semibold text-ink-2">대신 갈 만한 곳</p>
      <CandidateList courseId={courseId} position={stop.position} enabled={open} onPick={onPick} />

      <p className="mt-5 mb-2 text-body-sm font-semibold text-ink-2">짠이에게 맡기기</p>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={() => onStrategy("cheaper")} className="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-ink/20 bg-white text-body-sm font-semibold text-ink hover:border-tomato hover:bg-tomato-soft">
          <TrendingDown aria-hidden className="size-4" /> 더 저렴하게
        </button>
        <button type="button" onClick={() => onStrategy("closer")} className="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-ink/20 bg-white text-body-sm font-semibold text-ink hover:border-tomato hover:bg-tomato-soft">
          <MapPin aria-hidden className="size-4" /> 더 가까이
        </button>
      </div>
    </BottomSheet>
  );
}

/**
 * 한 자리의 대신 갈 곳 2~3곳: 얼마가 달라지는지와 한 줄 이유. 바꾸기 시트와 장소 결정 시트가 같이 쓴다.
 * onShown: 후보가 도착했을 때 몇 곳인지 (분석용)
 */
export function CandidateList({
  courseId,
  position,
  enabled,
  onPick,
  onShown,
  emptyDescription = "아래에서 짠이에게 맡기거나, 예산을 조금 넓혀 다시 짜 보세요.",
}: {
  courseId: string;
  position: number;
  enabled: boolean;
  onPick: (placeId: string) => void;
  onShown?: (count: number) => void;
  emptyDescription?: string;
}) {
  const candidates = useStopCandidates(courseId, position, enabled);
  const items = candidates.data?.items ?? [];
  const loaded = candidates.isSuccess;
  const shown = useRef(onShown);
  useEffect(() => {
    shown.current = onShown;
  }, [onShown]);
  useEffect(() => {
    if (loaded) shown.current?.(items.length);
  }, [loaded, items.length]);

  return (
    <>
      {candidates.isPending ? (
        <div className="grid gap-2" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[72px] rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState size="sm" mood="think" title="이 시간 · 예산 안에서는 대신할 곳이 적어요" description={emptyDescription} />
      ) : (
        <ul className="grid gap-2">
          {items.map((c) => (
            <li key={c.place.id}>
              <button
                type="button"
                onClick={() => onPick(c.place.id)}
                className="flex w-full items-center gap-3 rounded-xl border border-ink/15 bg-white p-2.5 text-left hover:border-tomato hover:bg-tomato-soft"
              >
                {c.place.thumbnail_url ? (
                  <span className="relative size-14 shrink-0 overflow-hidden rounded-lg">
                    <Image src={c.place.thumbnail_url} alt="" fill sizes="56px" className="object-cover" unoptimized={!canOptimize(c.place.thumbnail_url)} />
                  </span>
                ) : (
                  // 후보끼리 같은 분위기 이미지가 되풀이되면 고르기 어렵다 → 여기서는 실제 사진이 없으면 종류별 그림만 (docs/43)
                  <PlacePlaceholder kind={c.place.image?.placeholder_kind ?? c.role} className="size-14 shrink-0 rounded-lg" />
                )}
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-body font-semibold text-ink">{c.place.name}</b>
                  <span className="tabular block text-body-sm text-ink-2">
                    {c.est_price === 0 ? "무료" : won(c.est_price)} · <span className={c.price_delta < 0 ? "font-semibold text-mint" : ""}>{delta(c.price_delta)}</span>
                  </span>
                  <span className="block truncate text-caption text-muted-foreground">{c.line}</span>
                </span>
                <span className="shrink-0 rounded-full bg-tomato px-3 py-1.5 text-body-sm font-bold text-white">이걸로</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
