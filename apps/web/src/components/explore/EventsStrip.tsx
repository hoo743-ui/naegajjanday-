"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ChevronLeft, ChevronRight, MapPin } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { useEvents } from "@/lib/api/hooks";
import type { EventItem } from "@/lib/api/types";
import { dateRange, toKstIso, won } from "@/lib/format";
import { canOptimize, photoCredit } from "@/lib/photo-credit";
import { DdayBadge } from "./AttractionCard";

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** 사진이 없는 행사: 빈 칸 대신 날짜를 크게 찍은 티켓 한 장 (점선 = 절취선) */
function DateTicket({ startsOn }: { startsOn: string }) {
  const d = new Date(`${startsOn}T00:00:00+09:00`);
  return (
    <span className="grid size-full place-items-center rounded-[16px] border-[1.5px] border-dashed border-ink/20 bg-paper-2 text-center">
      <span>
        <span className="tabular block text-body-sm font-semibold text-muted-foreground">{d.getMonth() + 1}월</span>
        <span className="money block text-price text-ink">{d.getDate()}</span>
        <span className="block text-caption font-semibold text-muted-foreground">{WEEKDAY[d.getDay()]}요일부터</span>
      </span>
    </span>
  );
}

/**
 * 행사 한 칸: 흰 상자가 아니라 사진(또는 날짜 티켓)이 앞에 서고, 글은 그 아래에 (둘러보기 = 여행 잡지, docs/25 §5).
 */
function EventCard({ event }: { event: EventItem }) {
  const credit = photoCredit(event.thumbnail_url);
  // 공식 페이지가 없는 축제도 눌렀을 때 갈 곳이 있어야 한다 → 일정 검색으로 넘긴다
  const href = event.link_url ?? `https://search.naver.com/search.naver?query=${encodeURIComponent(`${event.title} 일정`)}`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="group block w-[240px] shrink-0 snap-start sm:w-[260px]"
      onClick={() => track("event_clicked", { event_id: event.id, from: "explore" })}
    >
      <span className="photo-edge relative block aspect-[4/3] overflow-hidden rounded-[16px]">
        {event.thumbnail_url ? (
          <>
            <Image src={event.thumbnail_url} alt="" fill unoptimized={!canOptimize(event.thumbnail_url)} sizes="260px" className="object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]" />
            {credit ? <span className="absolute right-2 bottom-1.5 rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95">{credit}</span> : null}
          </>
        ) : (
          <DateTicket startsOn={event.starts_on} />
        )}
        <span className="absolute top-2.5 left-2.5">
          <DdayBadge startsOn={event.starts_on} endsOn={event.ends_on} />
        </span>
      </span>
      <span className="mt-3 flex items-baseline justify-between gap-2">
        <span className="tabular text-caption font-semibold text-muted-foreground">{dateRange(event.starts_on, event.ends_on)}</span>
        <span className={event.is_free ? "text-caption font-semibold text-success" : "tabular text-caption font-semibold text-gold-ink"}>
          {event.is_free ? "무료" : event.price !== null ? won(event.price) : "유료"}
        </span>
      </span>
      <b className="mt-1 line-clamp-2 block text-body font-semibold text-ink">{event.title}</b>
      <span className="mt-1 flex items-center gap-1 text-body-sm text-muted-foreground">
        <MapPin aria-hidden className="size-3.5 shrink-0" />
        <span className="truncate">{[event.region?.name, event.venue].filter(Boolean).join(" · ")}</span>
      </span>
    </a>
  );
}

const MAX_STRIP_EVENTS = 30;

/**
 * 가로 목록: 저절로 흐르지 않는다(계속 움직이는 요소 금지, docs/25 §6). 좌우 버튼 · 손가락 · 방향키로 넘기고,
 * 아래의 얇은 막대가 지금 어디쯤인지 보여 준다.
 */
function useStrip() {
  // 목록은 데이터가 온 뒤에야 그려진다 → 요소를 state 로 받아(callback ref) 붙는 순간 계산이 돈다
  const [el, ref] = useState<HTMLUListElement | null>(null);
  const [progress, setProgress] = useState(0);
  const [canScroll, setCanScroll] = useState(false);

  useEffect(() => {
    if (!el) return;
    const measure = () => {
      const max = el.scrollWidth - el.clientWidth;
      setCanScroll(max > 8);
      setProgress(max > 0 ? el.scrollLeft / max : 0);
    };
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [el]);

  const page = (direction: -1 | 1) => el?.scrollBy({ left: direction * Math.max(260, el.clientWidth * 0.8), behavior: "smooth" });
  return { ref, progress, canScroll: el !== null && canScroll, page };
}

export function EventsStrip({ region }: { region?: string }) {
  const range = useMemo(() => {
    const now = new Date();
    return { from: toKstIso(now).slice(0, 10), to: toKstIso(new Date(now.getTime() + 7 * 86_400_000)).slice(0, 10) };
  }, []);
  const events = useEvents({ region, ...range });
  const strip = useStrip();

  return (
    <section aria-labelledby="events-heading" className="border-y border-ink/10 py-8">
      <div className="mb-5 flex items-end justify-between gap-3">
        <div>
          <h2 id="events-heading" className="text-h3 font-bold text-ink">
            이번 주 이벤트
          </h2>
          <p className="mt-1 text-body-sm text-muted-foreground">오늘부터 7일 안에 열리는 축제 · 전시 · 공연이에요.</p>
        </div>
        {strip.canScroll ? (
          <div className="flex shrink-0 gap-1.5">
            <button type="button" onClick={() => strip.page(-1)} aria-label="이전 이벤트" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 text-ink-2 hover:border-ink-2 hover:text-ink">
              <ChevronLeft aria-hidden className="size-5" />
            </button>
            <button type="button" onClick={() => strip.page(1)} aria-label="다음 이벤트" className="grid size-11 place-items-center rounded-full border border-line bg-white/70 text-ink-2 hover:border-ink-2 hover:text-ink">
              <ChevronRight aria-hidden className="size-5" />
            </button>
          </div>
        ) : null}
      </div>

      {events.isPending ? (
        <div className="flex gap-5 overflow-hidden" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="aspect-[4/3] w-[240px] shrink-0 rounded-[16px] sm:w-[260px]" />
          ))}
        </div>
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => void events.refetch()} size="sm" />
      ) : events.data.items.length === 0 ? (
        // 비어 있으면 막다른 길이 아니라 다음 행동 둘: 언제 가도 되는 곳(공원 · 산책) 또는 이 예산으로 하루 짜기
        <EmptyState size="sm" mood="think" title="이번 주에는 열리는 이벤트가 없어요" description="축제가 없어도 언제 가도 좋은 곳은 많아요. 다른 지역을 골라 보셔도 돼요.">
          <Button asChild variant="soft" size="md">
            <Link href={`/explore?type=park${region ? `&region=${encodeURIComponent(region)}` : ""}`}>공원 · 산책 먼저 보기</Link>
          </Button>
          <Button asChild variant="brand" size="md">
            <Link href="/plan">이 예산으로 하루 짜기</Link>
          </Button>
        </EmptyState>
      ) : (
        <>
          {/* tabIndex: 키보드만으로도 가로 스크롤 영역을 방향키로 넘길 수 있게 */}
          <ul ref={strip.ref} tabIndex={0} className="no-scrollbar -mx-1 flex snap-x gap-5 overflow-x-auto px-1 py-1" aria-label="이번 주 이벤트 목록">
            {/* 한 주에 200건이 넘기도 한다 — 가로 띠에는 가까운 것 30건이면 충분하고, 사진도 그만큼만 받는다 */}
            {events.data.items.slice(0, MAX_STRIP_EVENTS).map((event) => (
              <li key={event.id} className="flex">
                <EventCard event={event} />
              </li>
            ))}
          </ul>
          {strip.canScroll ? (
            <div aria-hidden className="mt-5 h-0.5 overflow-hidden rounded-full bg-ink/10">
              <div className="h-full w-1/4 rounded-full bg-ink" style={{ transform: `translateX(${strip.progress * 300}%)` }} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
