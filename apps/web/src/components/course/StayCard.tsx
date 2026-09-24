"use client";

import Image from "next/image";
import { useState } from "react";
import { BedDouble, ChevronDown, ExternalLink, MapPin, TrendingUp } from "lucide-react";
import { track } from "@/lib/analytics";
import { usePlaceSignals, useStays } from "@/lib/api/hooks";
import { bookingLinks, kstDate, type BookingLink } from "@/lib/booking";
import { distance } from "@/lib/format";
import type { NearbyPin } from "./map-shared";

interface StayCardProps {
  /** 그날 코스가 끝나는 지점: 숙소는 여기서 가까운 순으로 찾는다 */
  at: { lat: number; lng: number };
  day: number;
  /** 그날 코스의 시작 시각(ISO): 체크인 날짜. 1박으로 채운다 */
  startAt: string;
  /** 인원: 예약처 검색에 성인 수로 채운다 */
  adults: number;
  /** 지도에서 보기: 코스 지도에 띄운다. 없으면 지도 앱 검색으로 */
  onShow?: (pin: Omit<NearbyPin, "n">) => void;
}

const kakaoSearch = (query: string) => `https://map.kakao.com/link/search/${encodeURIComponent(query)}`;

/**
 * "오늘 밤 묵을 곳": 여행 일정에서 마지막 날이 아닌 날의 코스 아래에 붙는다.
 * 숙소를 고르면 바로 예약처로 (docs/46): 여기어때 · Booking.com 은 그날 날짜 · 1박 · 인원까지 채운 검색으로 연다.
 * 요금은 말하지 않는다 — 숙박 요금의 공식 데이터가 없다(API 의 price_note). 예산에도 넣지 않는다.
 * 사람들이 실제로 찾아가는 숙소면(티맵 내비 실측) 그 순위를 출처와 함께 적는다.
 */
/** 두 번째 예약처들은 한 줄 링크 뒤에 (창업자 2026-09-24: 결과 화면은 한 문장 + 누르면 아래에) */
function MoreBookings({ links, onClick }: { links: BookingLink[]; onClick: () => void }) {
  const [open, setOpen] = useState(false);
  if (links.length === 0) return null;
  return open ? (
    <>
      {links.map((l) => (
        <a
          key={l.key}
          href={l.url}
          target="_blank"
          rel="noreferrer"
          onClick={onClick}
          className="inline-flex h-9 items-center rounded-full border border-ink/15 px-3 text-body-sm font-semibold text-ink hover:border-ink"
        >
          {l.label}
        </a>
      ))}
    </>
  ) : (
    <button type="button" onClick={() => setOpen(true)} className="inline-flex h-9 items-center gap-0.5 px-1.5 text-body-sm font-semibold text-ink-2 underline decoration-ink/25 decoration-dotted underline-offset-4 hover:text-ink">
      다른 예약처 <ChevronDown aria-hidden className="size-3.5" />
    </button>
  );
}

export function StayCard({ at, day, startAt, adults, onShow }: StayCardProps) {
  const stays = useStays(at);
  const signals = usePlaceSignals(stays.data?.items.map((s) => s.id) ?? []);
  if (stays.isPending) return <p className="skeleton-shimmer h-[120px] rounded-card" aria-label="근처 숙소를 찾는 중" />;
  if (stays.isError || stays.data.items.length === 0) return null; // 등재 숙소가 없는 동네: 아무 말도 하지 않는다
  const checkin = kstDate(startAt);
  const nightLabel = `${Number(checkin.slice(5, 7))}/${Number(checkin.slice(8, 10))} 1박 · ${adults}명`;

  return (
    <section aria-labelledby="stay-card" className="rule-section gap-3.5">
      <h2 id="stay-card" className="flex items-center gap-2 text-body font-extrabold text-ink">
        <BedDouble aria-hidden className="size-4 text-blue-deep" />
        {day}일차 밤, 이 근처에서 묵는다면
      </h2>
      <ul className="grid gap-2.5 sm:grid-cols-2">
        {stays.data.items.map((stay) => {
          const links = bookingLinks(stay.name, checkin, adults);
          const primary = links[0]!; // 여기어때: 날짜 · 인원이 채워지는 국내 예약처
          const others = links.slice(1);
          const visited = signals.data?.items[stay.id]?.find((s) => s.kind === "visited");
          return (
            <li key={stay.id} className="grid gap-2 rounded-2xl border border-line p-2.5">
              <div className="flex items-center gap-3">
                <span className="relative block size-16 shrink-0 overflow-hidden rounded-xl bg-paper-2">
                  {stay.thumbnail_url ? <Image src={stay.thumbnail_url} alt="" fill sizes="64px" unoptimized className="object-cover" /> : null}
                </span>
                <span className="min-w-0">
                  <b className="block truncate text-body font-extrabold text-ink">{stay.name}</b>
                  <span className="tabular block text-caption text-muted-foreground">
                    {stay.category_label} · 코스 끝에서 {distance(stay.distance_m)}
                  </span>
                  {visited ? (
                    <span title={visited.source} className="flex items-center gap-1 text-caption font-semibold text-ink-2">
                      <TrendingUp aria-hidden className="size-3.5 shrink-0 text-blue-deep" />
                      <span className="truncate">{visited.label}</span>
                    </span>
                  ) : null}
                  {stay.photo_credit ? <span className="block text-caption text-muted-foreground">사진 ⓒ한국관광공사</span> : null}
                </span>
              {onShow ? (
                <button
                  type="button"
                  onClick={() => onShow({ id: stay.id, name: stay.name, lat: stay.lat, lng: stay.lng, kind: `${day}일차 밤 숙소 · 코스 끝에서 ${distance(stay.distance_m)}` })}
                  aria-label={`${stay.name} 지도에서 보기`}
                  className="ml-auto inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-ink/15 text-ink hover:border-ink"
                >
                  <MapPin aria-hidden className="size-4" />
                </button>
              ) : (
                <a href={kakaoSearch(stay.name)} target="_blank" rel="noreferrer" aria-label={`${stay.name} 지도에서 보기`} className="ml-auto inline-flex size-9 shrink-0 items-center justify-center rounded-full border border-ink/15 text-ink hover:border-ink">
                  <MapPin aria-hidden className="size-4" />
                </a>
              )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <a
                  href={primary.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => track("stay_clicked", { day })}
                  aria-label={`${stay.name} ${primary.label}에서 ${nightLabel} 예약하기`}
                  className="inline-flex h-9 items-center gap-1 rounded-full bg-ink px-3 text-body-sm font-bold text-white hover:bg-ink/85"
                >
                  예약하기 · {primary.label} <ExternalLink aria-hidden className="size-3.5" />
                </a>
                <MoreBookings links={others} onClick={() => track("stay_clicked", { day })} />
              </div>
            </li>
          );
        })}
      </ul>
      {/* 안내는 한 줄만: 요금 · 출처는 누르면 */}
      <details className="text-caption text-muted-foreground">
        <summary className="w-fit cursor-pointer underline decoration-ink/25 decoration-dotted underline-offset-4">예약처는 {nightLabel}으로 열어요 · 요금 안내</summary>
        <p className="mt-1">
          야놀자는 날짜를 그쪽에서 골라요. {stays.data.price_note} <span className="whitespace-nowrap">출처: {stays.data.source}</span>
        </p>
      </details>
    </section>
  );
}
