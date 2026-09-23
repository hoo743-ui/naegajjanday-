"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CalendarDays, MapPin, Star } from "lucide-react";
import { categoryImageFor, planHrefNear, useCategoryImages } from "@/lib/api/hooks";
import type { Attraction } from "@/lib/api/types";
import { dateRange, daysUntil, won } from "@/lib/format";
import { canOptimize, photoCredit } from "@/lib/photo-credit";
import { cn } from "@/lib/utils";
import { PlacePlaceholder } from "@/components/brand/PlacePlaceholder";
import { track } from "@/lib/analytics";
import { ATTRACTION_TYPE_META } from "./attraction-meta";
import { AttractionSheet } from "./AttractionSheet";

/** 둘러보기 유형 → 대표 사진을 찾을 업종 코드 */
const TYPE_CATEGORY: Record<string, string> = {
  park: "attraction.park",
  exhibition: "culture.gallery",
  festival: "culture.festival",
  culture: "culture",
  attraction: "attraction",
};

export function DdayBadge({ endsOn, startsOn }: { endsOn: string; startsOn?: string }) {
  const startsIn = startsOn ? daysUntil(startsOn) : 0;
  const left = daysUntil(endsOn);
  const text = startsIn > 0 ? `${startsIn}일 뒤 시작` : left < 0 ? "종료" : left === 0 ? "오늘 마감" : `D-${left}`;
  const urgent = startsIn <= 0 && left >= 0 && left <= 3;
  return (
    <span
      className={cn(
        "tabular rounded-full px-2.5 py-1 text-caption font-extrabold",
        urgent ? "bg-pink-soft text-pink-deep" : "bg-white/90 text-ink-2",
      )}
    >
      {text}
    </span>
  );
}

/**
 * feature: 목록 맨 위의 큰 한 장(둘러보기의 잡지 표지). 나머지는 3열 격자의 작은 칸.
 * kicker: 그 큰 장 위의 한 줄. "맨 먼저 볼 곳"은 동네를 골랐을 때만 말이 된다(그 동네에서 가장 많이 찾는 곳) —
 * 전국 목록의 첫 장은 수백 개 시군구 1위 중 하나일 뿐이라 이름을 붙이지 않는다.
 */
export function AttractionCard({ item, feature = false, kicker }: { item: Attraction; feature?: boolean; kicker?: string }) {
  const meta = ATTRACTION_TYPE_META[item.type] ?? ATTRACTION_TYPE_META.attraction;
  // API 는 region 을 주지 않는다 → 그 장소의 좌표를 출발점으로 넘겨야 정말 "이 근처"로 짠다
  const planHref = planHrefNear({ name: item.name, lat: item.lat, lng: item.lng });
  // 실사진이 없으면 검수한 업종 대표 사진을 쓴다. API 의 category 코드가 없으면 유형으로 대신 찾는다.
  const images = useCategoryImages().data?.items;
  const example = categoryImageFor(images, item.category ?? "") ?? categoryImageFor(images, TYPE_CATEGORY[item.type] ?? "attraction");
  const photo = item.thumbnail_url ?? example?.url ?? null;
  const credit = photoCredit(item.thumbnail_url);
  const [open, setOpen] = useState(false);
  const openDetail = () => {
    track("attraction_opened", { attraction_id: item.id, type: item.type });
    setOpen(true);
  };

  return (
    // 흰 상자 대신 사진이 앞에 선다 (docs/25 §5 둘러보기 = 여행 잡지). 카드 전체는 여전히 한 번에 눌린다
    <article className={cn("group relative flex h-full cursor-pointer flex-col", feature && "lg:grid lg:grid-cols-[1.4fr_1fr] lg:items-center lg:gap-12")}>
      <div className={cn("photo-edge relative overflow-hidden rounded-[20px] bg-gradient-to-br", feature ? "aspect-[3/2]" : "aspect-[4/3]", meta.gradient)}>
        {photo ? (
          <>
            <Image
              src={photo}
              alt=""
              fill
              unoptimized={!canOptimize(photo)}
              priority={feature}
              sizes={feature ? "(max-width: 1024px) 100vw, 660px" : "(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"}
              className="object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]"
            />
            {credit ? (
              <span className="absolute right-2 bottom-2 rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95">{credit}</span>
            ) : null}
            {!item.thumbnail_url && example ? (
              // 그 장소의 실제 사진이 아니라 같은 종류의 예시 사진임을 밝히고, 오픈 라이선스 조건대로 출처를 단다
              <a
                href={example.page_url ?? example.url}
                target="_blank"
                rel="noreferrer"
                className="absolute right-2 bottom-2 z-10 rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95 hover:bg-black/65"
                title="이 장소의 사진이 아니라 같은 종류의 예시 사진이에요"
              >
                예시 사진 · © {example.author}
              </a>
            ) : null}
          </>
        ) : (
          // 사진도 예시 사진도 없으면 우리 종이 위의 그림 (빈 상자처럼 보이지 않게, 사진인 척하지 않게)
          <PlacePlaceholder kind={item.type} size="lg" className="absolute inset-0" />
        )}
        <div className="absolute inset-x-3 top-3 flex items-center justify-between gap-2">
          <span className="rounded-full bg-ink/85 px-2.5 py-1 text-caption font-semibold text-white">{meta.label}</span>
          {item.period ? <DdayBadge startsOn={item.period.starts_on} endsOn={item.period.ends_on} /> : null}
        </div>
      </div>

      <div className={cn("flex flex-1 flex-col gap-2.5 pt-4", feature && "lg:pt-0")}>
        {feature && kicker ? <p className="text-body-sm font-semibold text-blue-deep">{kicker}</p> : null}
        <div className="flex items-start justify-between gap-3">
          <h3 className={cn("text-ink", feature ? "font-serif text-h1" : "text-body-lg font-semibold")}>
            {/* 카드 전체가 눌리도록 버튼의 클릭 영역을 카드까지 넓힌다(after:inset-0). 출처·코스 짜기 링크는 그 위(z-10)에 둔다. */}
            <button type="button" onClick={openDetail} aria-haspopup="dialog" className="text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-[20px] focus-visible:after:outline-[3px] focus-visible:after:outline-blue">
              {item.name}
            </button>
          </h3>
          {/* 요금 자료가 없는 곳(공공데이터에 입장료 칸이 빈 관광지 등)을 "0원"이라고 말하지 않는다 */}
          {item.is_free || item.price_per_person > 0 ? (
            <span
              className={cn(
                "tabular shrink-0 rounded-lg px-2 py-1 text-caption font-extrabold",
                item.is_free ? "bg-success-soft text-success" : "bg-gold-soft text-gold-ink",
              )}
            >
              {item.is_free ? "무료" : `1인 ${won(item.price_per_person)}`}
            </span>
          ) : null}
        </div>

        {item.summary ? <p className={cn("text-muted-foreground", feature ? "line-clamp-4 text-body" : "line-clamp-2 text-body-sm")}>{item.summary}</p> : null}

        <ul className="grid gap-1 text-body-sm font-semibold text-ink-2">
          <li className="flex items-center gap-1.5">
            <MapPin aria-hidden className="size-3.5 shrink-0 text-blue-deep" />
            <span className="truncate">{item.region ? `${item.region.name} · ${item.address}` : item.address}</span>
          </li>
          {item.period ? (
            <li className="tabular flex items-center gap-1.5">
              <CalendarDays aria-hidden className="size-3.5 shrink-0 text-blue-deep" />
              {dateRange(item.period.starts_on, item.period.ends_on)}
            </li>
          ) : null}
          {item.rating !== null ? (
            <li className="tabular flex items-center gap-1.5">
              <Star aria-hidden className="size-3.5 shrink-0 fill-gold text-gold-deep" />
              <span>
                <span className="sr-only">평점 </span>
                {item.rating.toFixed(1)}
              </span>
            </li>
          ) : null}
        </ul>

        {item.tags.length > 0 ? (
          <ul aria-label="태그" className="flex flex-wrap gap-1.5">
            {item.tags.map((tag) => (
              <li key={tag} className="rounded-full border border-line px-2.5 py-1 text-caption font-semibold text-ink-2">
                {tag}
              </li>
            ))}
          </ul>
        ) : null}

        <Link
          href={planHref}
          className="relative z-10 mt-auto inline-flex items-center gap-1 self-start pt-2 text-body-sm font-semibold text-blue-deep"
          aria-label={`${item.name} 근처로 코스 짜기`}
        >
          이 근처로 코스 짜기
          <ArrowRight aria-hidden className="size-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
      {open ? <AttractionSheet item={item} photo={photo} credit={credit} onClose={() => setOpen(false)} /> : null}
    </article>
  );
}
