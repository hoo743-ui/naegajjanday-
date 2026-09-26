"use client";

import { useState, type ReactNode } from "react";
import Image from "next/image";
import { distinctPhotos } from "@/lib/photo-key";
import { BadgeCheck, CalendarCheck, ChevronDown, Clock, ExternalLink, Globe, Navigation, Phone, Utensils } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { usePlaceDetail, usePlaceLinks } from "@/lib/api/hooks";
import type { PlaceSummary } from "@/lib/api/types";
import { won } from "@/lib/format";
import { photoCredit } from "@/lib/photo-credit";
import { cn } from "@/lib/utils";
import { kakaoSearchUrl, naverSearchUrl } from "./stop-links";

export type OutboundKind = "kakao" | "naver" | "official" | "phone" | "directions";

interface PlaceSheetProps {
  place: PlaceSummary | null;
  partySize: number;
  onClose: () => void;
  /**
   * 코스의 한 곳을 연 경우 (2026-09-26 창업자 "눌렀을 때 선택이 있어야"): 정보 페이지가 아니라 결정 시트.
   * why = 왜 이 곳인지 한 줄 · actions = 이 곳으로 할게요 / 다른 곳 보기 / 빼기. 그 아래 밖으로 나가는 길(예약 · 메뉴 · 길찾기 · 전화),
   * 메뉴판 · 영업시간은 한 줄로 접는다. 없으면(주변 장소) 예전처럼 정보만.
   */
  decision?: {
    why?: ReactNode;
    actions?: ReactNode;
    onDirections?: () => void;
    onOutbound?: (kind: OutboundKind) => void;
  };
}

const DOW = ["월", "화", "수", "목", "금", "토", "일"];
const MAX_PHOTOS = 6;

/**
 * 장소 상세: 우리가 실제로 가진 것만 보여 준다 — 조사된 메뉴판 가격 · 그 장소의 사진 · 전화 · 조사된 영업시간 ·
 * 영업 신고 연도 · 누가 보증했는지. 없는 항목은 칸째로 나오지 않는다(리뷰 · 별점은 데이터가 없어 자리를 만들지 않았다).
 * 나머지(최신 메뉴판 · 후기 · 예약)는 지도 앱이 더 잘 안다 → 그 장소의 페이지로 넘긴다 (docs/44).
 */
export function PlaceSheet({ place, partySize, onClose, decision }: PlaceSheetProps) {
  const detail = usePlaceDetail(place?.id ?? null);
  // 결정 시트에서만: 카카오 장소 페이지 · 공식 홈페이지를 서버가 찾아 둔 것 (못 찾으면 검색으로)
  const links = usePlaceLinks(decision ? "place" : undefined, decision ? place?.id : undefined);
  const [infoOpen, setInfoOpen] = useState(false);
  if (!place) return null;
  const d = detail.data;
  // 코스 밖의 주변 장소는 이름 · 좌표만 들고 온다 → 주소 · 업종 · 대표 사진은 상세에서 채운다
  const address = place.address || d?.address || "";
  const categoryName = place.category_name ?? d?.category_name;
  // 크기만 다른 같은 사진은 한 장으로 (docs/29 §20)
  const photos = distinctPhotos([place.thumbnail_url ?? d?.thumbnail_url ?? null, ...(d?.images ?? [])]).slice(0, MAX_PHOTOS);
  const years = d?.since_year ? new Date().getFullYear() - d.since_year : 0;
  const hours = (d?.opening_hours ?? []).filter((h) => h.is_closed || (h.open && h.close));
  const compact = Boolean(decision);
  const kakaoPage = links.data?.items.find((l) => l.kind === "place_page");
  const official = links.data?.items.find((l) => l.kind === "official");

  const trust = (
    <>
      {d?.since_year && years >= 3 ? (
        <p className={cn("tabular rounded-2xl bg-blue-soft text-body-sm font-bold text-blue-deep", compact ? "px-3 py-2" : "px-4 py-3")}>
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
    </>
  );

  const info = (
    <>
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
      ) : d && !d.is_free && d.kind !== "event" ? (
        // 무료로 보는 곳(명소 · 공원)에는 메뉴판이 없다 — 주변 명소를 열었을 때 "가게의 메뉴판"이라고 말하지 않는다
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
    </>
  );

  const out = "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-line bg-white px-3 text-body-sm font-semibold text-ink hover:border-ink-2";

  return (
    <Sheet open onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[440px]">
        {photos.length > 0 ? (
          <div className="flex shrink-0 snap-x snap-mandatory gap-1 overflow-x-auto bg-soft" aria-label={`${place.name} 사진 ${photos.length}장`}>
            {photos.map((url) => (
              // 결정 시트는 사진을 낮게: 고를 버튼이 첫 화면에 들어오게
              <span key={url} className={cn("relative block shrink-0 snap-center first:ml-0", compact ? "h-36 w-[62%]" : "aspect-[4/3] w-[86%]")}>
                <Image src={url} alt="" fill sizes="400px" unoptimized className="object-cover" />
                {photoCredit(url) ? <span className="absolute right-2 bottom-2 rounded-full bg-black/55 px-2 py-0.5 text-caption font-semibold text-white">{photoCredit(url)}</span> : null}
              </span>
            ))}
          </div>
        ) : null}

        <SheetHeader className={cn("gap-1 px-5 pb-0 text-left", compact ? "pt-4" : "pt-5")}>
          <SheetTitle className="text-h3 leading-tight font-extrabold">{place.name}</SheetTitle>
          <SheetDescription className="text-body-sm text-muted-foreground">
            {[categoryName, d?.licensed_as && d.licensed_as !== categoryName ? d.licensed_as : null, address].filter(Boolean).join(" · ")}
          </SheetDescription>
        </SheetHeader>

        {decision ? (
          <div className="grid gap-4 px-5 pt-3 pb-8">
            {decision.why}
            {trust}
            {decision.actions}

            {/* 밖으로: 예약 · 메뉴 · 후기는 그 장소의 페이지에 있다. 우리가 예약 · 결제를 하지 않는다 (docs/61) */}
            <nav aria-label="예약 · 길찾기" className="grid grid-cols-2 gap-2">
              <a
                href={kakaoPage?.url ?? kakaoSearchUrl({ name: place.name, address })}
                target="_blank"
                rel="noreferrer"
                onClick={() => decision.onOutbound?.("kakao")}
                className={cn(out, "col-span-2 border-ink bg-ink text-white hover:border-ink hover:opacity-90")}
              >
                <CalendarCheck aria-hidden className="size-4" /> 예약 · 메뉴 보기 <span className="font-medium text-white/70">카카오맵</span>
                <ExternalLink aria-hidden className="size-3.5" />
              </a>
              <a href={naverSearchUrl({ name: place.name, address })} target="_blank" rel="noreferrer" onClick={() => decision.onOutbound?.("naver")} className={out}>
                네이버 지도 <ExternalLink aria-hidden className="size-3.5" />
              </a>
              {decision.onDirections ? (
                <button type="button" onClick={decision.onDirections} className={out}>
                  <Navigation aria-hidden className="size-4" /> 길찾기
                </button>
              ) : null}
              {d?.phone ? (
                <a href={`tel:${d.phone.replace(/[^0-9+]/g, "")}`} onClick={() => decision.onOutbound?.("phone")} className={out} aria-label={`전화 ${d.phone}`}>
                  <Phone aria-hidden className="size-4 text-blue-deep" /> 전화
                </a>
              ) : null}
              {official ? (
                <a href={official.url} target="_blank" rel="noreferrer" onClick={() => decision.onOutbound?.("official")} className={out}>
                  <Globe aria-hidden className="size-4" /> 홈페이지
                </a>
              ) : null}
            </nav>
            <p className="-mt-2 text-caption text-muted-foreground">예약 · 결제는 지도 앱의 그 가게 페이지에서 해요.</p>

            {/* 메뉴판 · 영업시간: 한 줄로 접는다 ("한 문장 + 펼침") */}
            {d && (d.menus.length > 0 || hours.length > 0 || d.description) ? (
              <div className="grid gap-4 border-t border-dashed border-ink/15 pt-3">
                <button type="button" aria-expanded={infoOpen} onClick={() => setInfoOpen((v) => !v)} className="flex min-h-11 items-center justify-between text-left text-body-sm font-semibold text-ink-2 hover:text-ink">
                  메뉴 가격 · 영업시간 보기
                  <ChevronDown aria-hidden className={cn("size-4 transition-transform", infoOpen && "rotate-180")} />
                </button>
                {infoOpen ? info : null}
              </div>
            ) : null}
            {detail.isPending ? <p className="skeleton-shimmer h-16 rounded-2xl" aria-label="장소 정보를 불러오는 중" /> : null}
          </div>
        ) : (
          <div className="grid gap-5 px-5 pt-4 pb-8">
            {trust}
            {info}

            <div className="grid gap-2">
              {d?.phone ? (
                <a href={`tel:${d.phone.replace(/[^0-9+]/g, "")}`} className="inline-flex items-center justify-center gap-2 rounded-2xl border border-line px-4 py-3 text-body font-bold text-ink hover:border-blue-deep">
                  <Phone aria-hidden className="size-4 text-blue-deep" /> {d.phone}
                </a>
              ) : null}
              <a
                href={`https://map.kakao.com/link/search/${encodeURIComponent(`${address.split(" ").slice(0, 2).join(" ")} ${place.name}`.trim())}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-ink px-4 py-3 text-body font-bold text-white hover:opacity-90"
              >
                지도 앱에서 최신 메뉴 · 후기 보기 <ExternalLink aria-hidden className="size-4" />
              </a>
            </div>
            {detail.isPending ? <p className="skeleton-shimmer h-24 rounded-2xl" aria-label="장소 정보를 불러오는 중" /> : null}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
