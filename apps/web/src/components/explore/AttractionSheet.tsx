"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CalendarDays, ExternalLink, MapPin, Navigation, Search } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { track } from "@/lib/analytics";
import { planHrefNear } from "@/lib/api/hooks";
import type { Attraction } from "@/lib/api/types";
import { dateRange, won } from "@/lib/format";
import { canOptimize } from "@/lib/photo-credit";
import { ATTRACTION_TYPE_META } from "./attraction-meta";

interface AttractionSheetProps {
  item: Attraction | null;
  photo: string | null;
  /** 실제 사진일 때의 출처 표기(예시 사진이면 null) */
  credit?: string | null;
  onClose: () => void;
}

/**
 * 볼거리·축제 하나를 눌렀을 때 뜨는 상세 시트.
 * 우리가 가진 정보(기간·주소·요금·태그)를 먼저 보여 주고, 그 장소의 실제 사진·후기·공식 안내는
 * 지도 앱과 검색으로 한 번에 넘긴다 — 남의 콘텐츠를 긁어 오지 않고 연결만 한다.
 */
export function AttractionSheet({ item, photo, credit, onClose }: AttractionSheetProps) {
  if (!item) return null;
  const meta = ATTRACTION_TYPE_META[item.type] ?? ATTRACTION_TYPE_META.attraction;
  // 같은 이름이 전국에 많다 → 지역명을 붙여 검색해야 그 장소가 나온다
  const area = item.region?.name ?? item.address.split(" ").slice(0, 2).join(" ");
  const query = [area, item.name].filter(Boolean).join(" ");
  const Icon = meta.icon;
  const links = [
    {
      key: "map" as const,
      href: `https://map.kakao.com/link/search/${encodeURIComponent(query)}`,
      label: "지도에서 실제 사진 · 후기 보기",
      icon: MapPin,
    },
    {
      key: "route" as const,
      href: `https://map.kakao.com/link/to/${encodeURIComponent(item.name)},${item.lat},${item.lng}`,
      label: "여기까지 길찾기",
      icon: Navigation,
    },
    {
      key: "search" as const,
      href: `https://search.naver.com/search.naver?query=${encodeURIComponent(item.period ? `${item.name} 일정` : query)}`,
      label: item.period ? "공식 일정 · 프로그램 찾아보기" : "운영 시간 · 관련 정보 찾아보기",
      icon: Search,
    },
  ];
  // API 는 region 을 주지 않는다 → 그 장소의 좌표를 출발점으로 넘겨야 정말 "이 근처"로 짠다
  const planHref = planHrefNear({ name: item.name, lat: item.lat, lng: item.lng });

  return (
    <Sheet open onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-[440px]">
        <div className={`relative aspect-[16/10] shrink-0 bg-gradient-to-br ${meta.gradient}`}>
          {photo ? (
            <Image src={photo} alt="" fill unoptimized={!canOptimize(photo)} sizes="440px" className="object-cover" />
          ) : (
            <div aria-hidden className="absolute inset-0 grid place-items-center">
              <span className="grid size-16 place-items-center rounded-[22px] bg-white/70 text-blue-deep shadow-soft">
                <Icon className="size-8" />
              </span>
            </div>
          )}
          {photo && credit ? <span className="absolute right-2.5 bottom-2 rounded-md bg-black/45 px-1.5 py-0.5 text-[10.5px] font-medium text-white/95">{credit}</span> : null}
          <span className="absolute top-3 left-3 rounded-full bg-ink/85 px-2.5 py-1 text-xs font-extrabold text-white">{meta.label}</span>
        </div>

        <SheetHeader className="gap-1.5 px-5 pt-5 pb-0 text-left">
          <SheetTitle className="text-xl leading-snug font-extrabold tracking-tight">{item.name}</SheetTitle>
          <SheetDescription className="text-sm text-muted-foreground">{item.summary || `${item.region?.name ?? ""} ${meta.label}`.trim()}</SheetDescription>
        </SheetHeader>

        <div className="grid gap-5 px-5 pt-4 pb-6">
          <ul className="grid gap-2 rounded-2xl bg-soft p-4 text-sm font-bold text-ink-2">
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
                <span aria-hidden className="grid size-4 shrink-0 place-items-center text-[13px] text-blue-deep">₩</span>
                {item.is_free ? "무료" : `1인 ${won(item.price_per_person)}`}
              </li>
            ) : null}
          </ul>

          {item.tags.length > 0 ? (
            <ul aria-label="태그" className="flex flex-wrap gap-1.5">
              {item.tags.map((tag) => (
                <li key={tag} className="rounded-full bg-soft px-2.5 py-1 text-xs font-bold text-ink-2">
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
                onClick={() => track("attraction_link_clicked", { attraction_id: item.id, to: l.key })}
                className="flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3.5 text-sm font-extrabold text-ink transition-colors hover:border-blue/50 hover:bg-blue-soft"
              >
                <l.icon aria-hidden className="size-4.5 shrink-0 text-blue-deep" />
                <span className="min-w-0 flex-1">{l.label}</span>
                <ExternalLink aria-hidden className="size-4 shrink-0 text-muted-foreground" />
              </a>
            ))}
          </nav>

          <Link
            href={planHref}
            className="bg-grad inline-flex h-13 items-center justify-center gap-1.5 rounded-full px-6 text-[15px] font-extrabold text-white shadow-card"
          >
            이 근처로 코스 짜기 <ArrowRight aria-hidden className="size-4" />
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}
