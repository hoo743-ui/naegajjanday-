"use client";

import { useState } from "react";
import Image from "next/image";
import { ChevronRight, Navigation } from "lucide-react";
import { PlaceSheet } from "@/components/course/PlaceSheet";
import { track } from "@/lib/analytics";
import { useHotPlaces } from "@/lib/api/hooks";
import type { HotPlace, PlaceSummary } from "@/lib/api/types";

const asSummary = (p: HotPlace): PlaceSummary => ({
  id: p.id,
  name: p.name,
  category: p.category,
  category_name: p.category_name ?? undefined,
  lat: p.lat,
  lng: p.lng,
  address: p.address ?? "",
  thumbnail_url: p.thumbnail_url,
  rating: null,
  review_count: 0,
  price_per_person: null,
  is_free: p.is_free,
  tags: [],
  kind: "place",
});

/**
 * "여기서는 어디를 가요?" — 고른 지역에서 사람들이 실제로 많이 찾아간 곳. 별점이나 후기가 아니라
 * 내비게이션 목적지 실측 순위다(출처를 적는다). 누르면 우리가 가진 상세(사진 · 영업시간 · 메뉴 · 표식)가 열린다.
 * 자료가 없는 지역이면 아무것도 그리지 않는다.
 */
export function HotPlaces({ regionSlug, partySize }: { regionSlug: string; partySize: number }) {
  const hot = useHotPlaces(regionSlug);
  const [open, setOpen] = useState<HotPlace | null>(null);
  const items = hot.data?.items ?? [];
  if (items.length === 0) return null;
  const widened = hot.data && hot.data.scope !== hot.data.region;

  return (
    <section aria-labelledby="hot-places" className="border-t-[1.5px] border-dashed border-ink/20 pt-6">
      <h3 id="hot-places" className="text-body font-extrabold text-ink">
        {hot.data?.scope}에서 사람들이 많이 가는 곳
      </h3>
      <p className="mt-0.5 text-caption text-muted-foreground">
        {widened ? `${hot.data?.region}만의 자료는 적어서 ${hot.data?.scope} 전체에서 골랐어요. ` : ""}
        후기가 아니라 내비게이션으로 실제 찾아간 순위예요. 누르면 자세히 볼 수 있어요.
      </p>
      <ol className="mt-3 grid gap-2 sm:grid-cols-2">
        {items.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              aria-haspopup="dialog"
              aria-label={`${p.name} 자세히 보기`}
              onClick={() => {
                track("hot_place_opened", { region: regionSlug, place_id: p.id, rank: p.rank });
                setOpen(p);
              }}
              className="flex w-full items-center gap-3 rounded-2xl border border-line p-2.5 text-left transition-colors hover:border-blue-deep hover:bg-blue-soft"
            >
              <span className="relative grid size-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-paper-2 text-blue-deep">
                {p.thumbnail_url ? <Image src={p.thumbnail_url} alt="" fill sizes="48px" unoptimized className="object-cover" /> : <Navigation aria-hidden className="size-5" />}
              </span>
              <span className="min-w-0 flex-1">
                <b className="block truncate text-body font-extrabold text-ink">{p.name}</b>
                <span className="tabular block truncate text-caption text-muted-foreground">
                  {[p.category_name, `찾아간 순위 ${p.rank}위`, p.is_free ? "무료" : null].filter(Boolean).join(" · ")}
                </span>
              </span>
              <ChevronRight aria-hidden className="size-4 shrink-0 text-muted-foreground" />
            </button>
          </li>
        ))}
      </ol>
      <p className="mt-2.5 text-caption text-muted-foreground">자료: {hot.data?.source}</p>
      <PlaceSheet place={open ? asSummary(open) : null} partySize={partySize} onClose={() => setOpen(null)} />
    </section>
  );
}
