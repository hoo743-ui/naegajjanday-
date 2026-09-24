"use client";

import Link from "next/link";
import { ArrowRight, CalendarDays, ExternalLink, Globe, MapPin, MessageSquareText, Navigation, Search, type LucideIcon } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { track } from "@/lib/analytics";
import { planHrefNear, usePlaceLinks } from "@/lib/api/hooks";
import type { Attraction, ImageRef } from "@/lib/api/types";
import { dateRange, won } from "@/lib/format";
import { PlacePhoto } from "@/components/brand/PlacePhoto";
import { ATTRACTION_TYPE_META } from "./attraction-meta";

interface AttractionSheetProps {
  item: Attraction | null;
  /** 카드와 같은 그림 (docs/43): 실제 사진이면 출처, 분위기 이미지면 그 표시까지 같이 간다 */
  image: ImageRef;
  onClose: () => void;
}

const LINK_ICON: Record<string, LucideIcon> = { official: Globe, place_page: MapPin, blog: MessageSquareText, route: Navigation, search: Search };

/**
 * 볼거리·축제 하나를 눌렀을 때 뜨는 상세 시트.
 * 우리가 가진 정보(기간·주소·요금·태그)를 먼저 보여 주고, 공식 홈페이지 · 후기는 **그 장소의 페이지로 바로** 보낸다
 * (docs/44: 서버가 카카오 로컬 · 관광공사 API 로 찾은 주소). 찾는 동안과 못 찾았을 때는 예전의 검색 링크.
 * 남의 콘텐츠를 긁어 오지 않고 연결만 한다.
 */
export function AttractionSheet({ item, image, onClose }: AttractionSheetProps) {
  const resolved = usePlaceLinks(item?.kind, item?.id);
  if (!item) return null;
  const meta = ATTRACTION_TYPE_META[item.type] ?? ATTRACTION_TYPE_META.attraction;
  // 같은 이름이 전국에 많다 → 지역명을 붙여 검색해야 그 장소가 나온다
  const area = item.region?.name ?? item.address.split(" ").slice(0, 2).join(" ");
  const query = [area, item.name].filter(Boolean).join(" ");
  const fallback = [
    { key: "place_page", href: `https://map.kakao.com/link/search/${encodeURIComponent(query)}`, label: "지도에서 실제 사진 · 후기 보기", note: null },
    { key: "route", href: `https://map.kakao.com/link/to/${encodeURIComponent(item.name)},${item.lat},${item.lng}`, label: "여기까지 길찾기", note: null },
    {
      key: "search",
      href: `https://search.naver.com/search.naver?query=${encodeURIComponent(item.period ? `${item.name} 일정` : query)}`,
      label: item.period ? "공식 일정 · 프로그램 찾아보기" : "운영 시간 · 관련 정보 찾아보기",
      note: null,
    },
  ];
  // 서버가 찾은 링크: 그 장소의 페이지면 출처만, 검색 결과면 "검색 결과"라고 밝힌다
  const links = resolved.data?.items.length
    ? resolved.data.items.map((l) => ({ key: l.kind, href: l.url, label: l.label, note: l.exact ? l.source : `${l.source} 검색 결과` }))
    : fallback;
  // API 는 region 을 주지 않는다 → 그 장소의 좌표를 출발점으로 넘겨야 정말 "이 근처"로 짠다
  const planHref = planHrefNear({ name: item.name, lat: item.lat, lng: item.lng });

  return (
    <Sheet open onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[440px]">
        <div className={`relative aspect-[16/10] shrink-0 bg-gradient-to-br ${meta.gradient}`}>
          <PlacePhoto image={image} size="lg" sizes="440px" className="absolute inset-0" />
          <span className="absolute top-3 left-3 rounded-full bg-ink/85 px-2.5 py-1 text-caption font-semibold text-white">{meta.label}</span>
        </div>

        <SheetHeader className="gap-1.5 px-5 pt-5 pb-0 text-left">
          <SheetTitle className="text-h3 leading-snug font-extrabold">{item.name}</SheetTitle>
          <SheetDescription className="text-body-sm text-muted-foreground">{item.summary || `${item.region?.name ?? ""} ${meta.label}`.trim()}</SheetDescription>
        </SheetHeader>

        <div className="grid gap-5 px-5 pt-4 pb-6">
          <ul className="grid gap-2 rounded-2xl bg-soft p-4 text-body-sm font-semibold text-ink-2">
            <li className="flex items-start gap-2">
              <MapPin aria-hidden className="mt-0.5 size-4 shrink-0 text-blue-deep" />
              <span>{item.address || item.region?.name || "주소 정보 없음"}</span>
            </li>
            {item.period ? (
              <li className="tabular flex items-center gap-2">
                <CalendarDays aria-hidden className="size-4 shrink-0 text-blue-deep" />
                {dateRange(item.period.starts_on, item.period.ends_on)}
              </li>
            ) : null}
            {item.is_free || item.price_per_person > 0 ? (
              <li className="tabular flex items-center gap-2">
                <span aria-hidden className="grid size-4 shrink-0 place-items-center text-body-sm text-blue-deep">₩</span>
                {item.is_free ? "무료" : `1인 ${won(item.price_per_person)}`}
              </li>
            ) : null}
          </ul>

          {item.tags.length > 0 ? (
            <ul aria-label="태그" className="flex flex-wrap gap-1.5">
              {item.tags.map((tag) => (
                <li key={tag} className="rounded-full bg-soft px-2.5 py-1 text-caption font-semibold text-ink-2">
                  {tag}
                </li>
              ))}
            </ul>
          ) : null}

          <nav aria-label="관련 페이지" className="grid gap-2">
            {links.map((l) => (
              <a
                key={l.key}
                href={l.href}
                target="_blank"
                rel="noreferrer"
                onClick={() => track("attraction_link_clicked", { attraction_id: item.id, to: l.key as "official" | "place_page" | "blog" | "route" | "search" })}
                className="flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3.5 text-body-sm font-semibold text-ink transition-colors hover:border-blue/50 hover:bg-blue-soft"
              >
                {(() => {
                  const Icon = LINK_ICON[l.key] ?? Search;
                  return <Icon aria-hidden className="size-4.5 shrink-0 text-blue-deep" />;
                })()}
                <span className="min-w-0 flex-1">
                  {l.label}
                  {l.note ? <span className="block text-caption font-medium text-muted-foreground">{l.note}</span> : null}
                </span>
                <ExternalLink aria-hidden className="size-4 shrink-0 text-muted-foreground" />
              </a>
            ))}
          </nav>

          <Link
            href={planHref}
            className="bg-grad inline-flex h-13 items-center justify-center gap-1.5 rounded-full px-6 text-body font-extrabold text-white shadow-card"
          >
            이 근처로 코스 짜기 <ArrowRight aria-hidden className="size-4" />
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}
