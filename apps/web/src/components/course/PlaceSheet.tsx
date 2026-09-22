"use client";

import Image from "next/image";
import { distinctPhotos } from "@/lib/photo-key";
import { BadgeCheck, Clock, ExternalLink, Phone, Utensils } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { usePlaceDetail } from "@/lib/api/hooks";
import type { PlaceSummary } from "@/lib/api/types";
import { won } from "@/lib/format";
import { photoCredit } from "@/lib/photo-credit";

interface PlaceSheetProps {
  place: PlaceSummary | null;
  partySize: number;
  onClose: () => void;
}

const DOW = ["월", "화", "수", "목", "금", "토", "일"];
const MAX_PHOTOS = 6;

/**
 * 장소 상세: 우리가 실제로 가진 것만 보여 준다 — 조사된 메뉴판 가격 · 그 장소의 사진 · 전화 · 조사된 영업시간 ·
 * 영업 신고 연도 · 누가 보증했는지. 없는 항목은 칸째로 나오지 않는다(리뷰 · 별점은 데이터가 없어 자리를 만들지 않았다).
 * 나머지(최신 메뉴판 · 후기)는 지도 앱이 더 잘 안다 → 맨 아래에서 넘긴다.
 */
export function PlaceSheet({ place, partySize, onClose }: PlaceSheetProps) {
  const detail = usePlaceDetail(place?.id ?? null);
  if (!place) return null;
  const d = detail.data;
  // 크기만 다른 같은 사진은 한 장으로 (docs/29 §20)
  const photos = distinctPhotos([place.thumbnail_url, ...(d?.images ?? [])]).slice(0, MAX_PHOTOS);
  const years = d?.since_year ? new Date().getFullYear() - d.since_year : 0;
  const hours = (d?.opening_hours ?? []).filter((h) => h.is_closed || (h.open && h.close));

  return (
    <Sheet open onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[440px]">
        {photos.length > 0 ? (
          <div className="flex shrink-0 snap-x snap-mandatory gap-1 overflow-x-auto bg-soft" aria-label={`${place.name} 사진 ${photos.length}장`}>
            {photos.map((url) => (
              <span key={url} className="relative block aspect-[4/3] w-[86%] shrink-0 snap-center first:ml-0">
                <Image src={url} alt="" fill sizes="400px" unoptimized className="object-cover" />
                {photoCredit(url) ? <span className="absolute right-2 bottom-2 rounded-full bg-black/55 px-2 py-0.5 text-caption font-semibold text-white">{photoCredit(url)}</span> : null}
              </span>
            ))}
          </div>
        ) : null}

        <SheetHeader className="gap-1 px-5 pt-5 pb-0 text-left">
          <SheetTitle className="text-h3 leading-tight font-extrabold">{place.name}</SheetTitle>
          <SheetDescription className="text-body-sm text-muted-foreground">
            {[place.category_name, d?.licensed_as && d.licensed_as !== place.category_name ? d.licensed_as : null, place.address].filter(Boolean).join(" · ")}
          </SheetDescription>
        </SheetHeader>

        <div className="grid gap-5 px-5 pt-4 pb-8">
          {d?.since_year && years >= 3 ? (
            <p className="tabular rounded-2xl bg-blue-soft px-4 py-3 text-body-sm font-bold text-blue-deep">
              {d.since_year}년부터 {years}년째 영업 중이에요. <span className="font-medium text-ink-2">(영업 신고 기준)</span>
            </p>
          ) : null}

          {d && d.marks.length > 0 ? (
            <section aria-label="공적 표식" className="grid gap-1.5">
              {d.marks.map((m) => (
                <p key={m.tag} className="flex items-start gap-2 text-body-sm">
                  <BadgeCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-blue-deep" />
                  <span>
                    <b className="font-extrabold">{m.tag}</b> <span className="text-ink-2">— {m.by}</span>
                  </span>
                </p>
              ))}
            </section>
          ) : null}

          {d && d.menus.length > 0 ? (
            <section aria-labelledby="place-menu" className="receipt-wrap rounded-2xl border border-line p-4">
              <h3 id="place-menu" className="flex items-center gap-1.5 text-body-sm font-semibold text-muted-foreground">
                <Utensils aria-hidden className="size-3.5" /> 조사된 메뉴판 가격
              </h3>
              <ul className="tabular mt-2 grid gap-1.5">
                {d.menus.slice(0, 8).map((m) => (
                  <li key={`${m.name}-${m.price}`} className="flex items-baseline gap-2 text-body">
                    <span className="min-w-0 truncate font-semibold text-ink">{m.name}</span>
                    <span aria-hidden className="receipt-leader flex-1" />
                    <span className="font-extrabold text-gold-ink">{won(m.price)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2.5 text-caption text-muted-foreground">
                행정안전부 착한가격업소 조사 가격이에요. {partySize}명이면 가장 싼 메뉴로 {won(Math.min(...d.menus.map((m) => m.price)) * partySize)}부터예요. 가격은 바뀔 수 있어요.
              </p>
            </section>
          ) : d ? (
            <p className="rounded-2xl bg-soft px-4 py-3 text-body-sm text-ink-2">
              이 가게의 메뉴판 가격은 아직 조사된 것이 없어요. 코스의 금액은 같은 지역 · 같은 업종의 평균가예요.
            </p>
          ) : null}

          {hours.length > 0 ? (
            <section aria-labelledby="place-hours">
              <h3 id="place-hours" className="flex items-center gap-1.5 text-body-sm font-semibold text-muted-foreground">
                <Clock aria-hidden className="size-3.5" /> 영업시간
              </h3>
              <ul className="tabular mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-body-sm text-ink-2">
                {hours.map((h) => (
                  <li key={h.dow}>
                    <b className="mr-1.5 font-extrabold text-ink">{DOW[h.dow] ?? h.dow}</b>
                    {h.is_closed ? "쉬는 날" : `${h.open} ~ ${h.close}`}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {d?.description ? <p className="text-body-sm whitespace-pre-line text-ink-2">{d.description}</p> : null}

          <div className="grid gap-2">
            {d?.phone ? (
              <a href={`tel:${d.phone.replace(/[^0-9+]/g, "")}`} className="inline-flex items-center justify-center gap-2 rounded-2xl border border-line px-4 py-3 text-body font-bold text-ink hover:border-blue-deep">
                <Phone aria-hidden className="size-4 text-blue-deep" /> {d.phone}
              </a>
            ) : null}
            <a
              href={`https://map.kakao.com/link/search/${encodeURIComponent(`${place.address?.split(" ").slice(0, 2).join(" ") ?? ""} ${place.name}`.trim())}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-ink px-4 py-3 text-body font-bold text-white hover:opacity-90"
            >
              지도 앱에서 최신 메뉴 · 후기 보기 <ExternalLink aria-hidden className="size-4" />
            </a>
          </div>
          {detail.isPending ? <p className="skeleton-shimmer h-24 rounded-2xl" aria-label="장소 정보를 불러오는 중" /> : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
