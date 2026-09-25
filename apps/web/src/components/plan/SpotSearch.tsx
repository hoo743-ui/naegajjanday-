"use client";

import { useId, useState } from "react";
import { Search, ShoppingBag } from "lucide-react";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounced, useSpots, type Spot } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const row = "flex w-full items-center gap-3 border-b border-line px-2 py-3.5 text-left transition-colors duration-150 hover:bg-white/70";

/**
 * 가게 · 매장 · 랜드마크 이름으로 찾기 (docs/51 B1). 우리 장소 먼저, 없으면 지도 검색 — 고르면 onPick.
 * 위저드의 "꼭 들를 곳이 있어요"와 결과 화면의 설정 바꾸기가 같이 쓴다.
 */
export function SpotSearch({ onPick }: { onPick: (spot: Spot) => void }) {
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 200);
  const spots = useSpots(query);
  const searchId = useId();
  const items = spots.data?.items ?? [];

  return (
    <div className="grid gap-2">
      <label htmlFor={searchId} className="sr-only">
        꼭 들를 곳 검색
      </label>
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
        <input
          id={searchId}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="매장 · 가게 이름 (예: 애플 가로수길)"
          autoComplete="off"
          className="h-12 w-full min-w-0 rounded-2xl border border-input bg-white pr-4 pl-12 text-body font-semibold shadow-soft placeholder:font-medium placeholder:text-muted-foreground focus-visible:border-tomato"
        />
      </div>
      <div aria-label="찾은 곳" aria-live="polite">
        {query.length < 2 ? null : spots.isPending ? (
          <div className="grid gap-1" aria-busy="true">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-[56px] rounded-md" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState size="sm" mood="think" title={`‘${query}’ 은(는) 찾지 못했어요`} description="이름에 동네를 붙여 다시 찾아볼까요? (예: 애플 가로수길)" />
        ) : (
          <div className="grid">
            {items.map((sp) => (
              <button
                key={`${sp.source}:${sp.name}:${sp.lat}`}
                type="button"
                onClick={() => {
                  onPick(sp);
                  setQ("");
                }}
                className={row}
              >
                <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-paper-2 text-ink">
                  <ShoppingBag aria-hidden className="size-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-body font-semibold">{sp.name}</b>
                  <span className="block truncate text-body-sm text-muted-foreground">{sp.address ?? "주소 정보 없음"}</span>
                </span>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold", sp.source === "ours" ? "bg-blue-soft text-blue-deep" : "bg-paper-2 text-ink-2")}>
                  {sp.source === "ours" ? "우리 장소" : "지도 검색"}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
