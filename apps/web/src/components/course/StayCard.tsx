"use client";

import Image from "next/image";
import { BedDouble } from "lucide-react";
import { track } from "@/lib/analytics";
import { useStays } from "@/lib/api/hooks";
import { distance } from "@/lib/format";

interface StayCardProps {
  /** 그날 코스가 끝나는 지점: 숙소는 여기서 가까운 순으로 찾는다 */
  at: { lat: number; lng: number };
  day: number;
}

const kakaoSearch = (query: string) => `https://map.kakao.com/link/search/${encodeURIComponent(query)}`;

/**
 * "오늘 밤 묵을 곳": 여행 일정에서 마지막 날이 아닌 날의 코스 아래에 붙는다.
 * 요금은 말하지 않는다 — 숙박 요금의 공식 데이터가 없다(API 의 price_note 를 그대로 보여 준다). 예산에도 넣지 않는다.
 */
export function StayCard({ at, day }: StayCardProps) {
  const stays = useStays(at);
  if (stays.isPending) return <p className="skeleton-shimmer h-[120px] rounded-card" aria-label="근처 숙소를 찾는 중" />;
  if (stays.isError || stays.data.items.length === 0) return null; // 등재 숙소가 없는 동네: 아무 말도 하지 않는다

  return (
    <section aria-labelledby="stay-card" className="rule-section gap-3.5">
      <h2 id="stay-card" className="flex items-center gap-2 text-[15px] font-extrabold text-ink">
        <BedDouble aria-hidden className="size-4 text-blue-deep" />
        {day}일차 밤, 이 근처에서 묵는다면
      </h2>
      <ul className="grid gap-2.5 sm:grid-cols-2">
        {stays.data.items.map((stay) => (
          <li key={stay.id}>
            <a href={kakaoSearch(stay.name)} target="_blank" rel="noreferrer" onClick={() => track("stay_clicked", { day })} className="flex items-center gap-3 rounded-2xl border border-line p-2.5 hover:border-blue-deep">
              <span className="relative block size-16 shrink-0 overflow-hidden rounded-xl bg-paper-2">
                {stay.thumbnail_url ? <Image src={stay.thumbnail_url} alt="" fill sizes="64px" unoptimized className="object-cover" /> : null}
              </span>
              <span className="min-w-0">
                <b className="block truncate text-[14.5px] font-extrabold text-ink">{stay.name}</b>
                <span className="tabular block text-[12.5px] text-muted-foreground">
                  {stay.category_label} · 코스 끝에서 {distance(stay.distance_m)}
                </span>
                {stay.photo_credit ? <span className="block text-[11px] text-muted-foreground">사진 ⓒ한국관광공사</span> : null}
              </span>
            </a>
          </li>
        ))}
      </ul>
      <p className="text-[12.5px] leading-relaxed text-muted-foreground">
        {stays.data.price_note} <span className="whitespace-nowrap">출처: {stays.data.source}</span>
      </p>
    </section>
  );
}
