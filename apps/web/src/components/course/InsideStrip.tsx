"use client";

import { useId, useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { useInside } from "@/lib/api/hooks";
import { roleLabel, won } from "@/lib/format";
import { cn } from "@/lib/utils";

/** 거리 · 시장 스톱: 그 안에서 가볼 만한 곳이 있는 종류 (API suggestions.json › inside 와 같은 목록) */
export const INSIDE_CATEGORIES = new Set(["attraction.street", "attraction.market", "attraction", "attraction.landmark"]);

/**
 * 이 골목에서 가볼 만한 곳 (2026-09-26 창업자: 먹자골목이면 먹자골목의 가볼 만한 곳을 추천하는 게 정상).
 * 한 줄로 접혀 있다가 누르면 서버에 묻는다 — 결과 화면은 한 문장씩(docs/46).
 */
export function InsideStrip({ courseId, position, name }: { courseId: string; position: number; name: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const inside = useInside(courseId, position, open);
  const items = inside.data?.items ?? [];
  return (
    <div className="mt-2">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls={panelId} className="flex max-w-full items-center gap-1 text-left text-body-sm font-semibold text-blue-deep hover:underline">
        <Sparkles aria-hidden className="size-3.5 shrink-0" />
        <span className="truncate">{name}에서 가볼 만한 곳</span>
        <ChevronDown aria-hidden className={cn("size-3.5 shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div id={panelId} className="mt-2" aria-live="polite">
          {inside.isPending ? (
            <p className="text-body-sm text-muted-foreground">찾는 중…</p>
          ) : items.length === 0 ? (
            <p className="text-body-sm text-muted-foreground">이 시간에 열려 있는, 소개할 만한 곳을 찾지 못했어요.</p>
          ) : (
            <ul className="grid gap-1.5">
              {items.map((i) => (
                <li key={i.place.id} className="flex items-baseline justify-between gap-3 rounded-xl bg-soft px-3 py-2 text-body-sm">
                  <span className="min-w-0">
                    <b className="font-semibold text-ink">{i.place.name}</b>
                    <span className="ml-1.5 text-caption text-muted-foreground">
                      {roleLabel(i.role as never)} · {i.reason}
                    </span>
                  </span>
                  {i.price_per_person ? <span className="tabular shrink-0 text-caption text-ink-2">1인 약 {won(i.price_per_person)}</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
