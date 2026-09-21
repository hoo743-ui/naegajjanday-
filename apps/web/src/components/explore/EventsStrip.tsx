"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { useReducedMotion } from "motion/react";
import { CalendarDays, ChevronLeft, ChevronRight, MapPin } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/mascot/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { track } from "@/lib/analytics";
import { useEvents } from "@/lib/api/hooks";
import type { EventItem } from "@/lib/api/types";
import { dateRange, toKstIso, won } from "@/lib/format";
import { canOptimize, photoCredit } from "@/lib/photo-credit";
import { DdayBadge } from "./AttractionCard";

function EventCard({ event }: { event: EventItem }) {
  const credit = photoCredit(event.thumbnail_url);
  // 공식 페이지가 없는 축제도 눌렀을 때 갈 곳이 있어야 한다 → 일정 검색으로 넘긴다
  const href = event.link_url ?? `https://search.naver.com/search.naver?query=${encodeURIComponent(`${event.title} 일정`)}`;
  const body = (
    <>
      {event.thumbnail_url ? (
        <div className="relative -mx-4 -mt-4 mb-3 aspect-[16/9] overflow-hidden rounded-t-[20px]">
          <Image src={event.thumbnail_url} alt="" fill unoptimized={!canOptimize(event.thumbnail_url)} sizes="280px" className="object-cover" />
          {credit ? <span className="absolute right-2 bottom-1.5 rounded-md bg-black/45 px-1.5 py-0.5 text-[10px] font-medium text-white/95">{credit}</span> : null}
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-2">
        <span className={event.is_free ? "text-xs font-extrabold text-success" : "tabular text-xs font-extrabold text-gold-ink"}>
          {event.is_free ? "무료" : event.price !== null ? won(event.price) : "유료"}
        </span>
        <DdayBadge startsOn={event.starts_on} endsOn={event.ends_on} />
      </div>
      <h3 className="mt-2 line-clamp-2 text-base leading-snug font-extrabold tracking-tight text-ink">{event.title}</h3>
      <p className="tabular mt-2 flex items-center gap-1.5 text-[13px] font-bold text-ink-2">
        <CalendarDays aria-hidden className="size-3.5 shrink-0 text-blue-deep" />
        {dateRange(event.starts_on, event.ends_on)}
      </p>
      <p className="mt-0.5 flex items-center gap-1.5 text-[13px] font-bold text-muted-foreground">
        <MapPin aria-hidden className="size-3.5 shrink-0" />
        <span className="truncate">{[event.region?.name, event.venue].filter(Boolean).join(" · ")}</span>
      </p>
    </>
  );
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="glass block h-full w-[260px] shrink-0 snap-start overflow-hidden p-4 sm:w-[280px]"
      onClick={() => track("event_clicked", { event_id: event.id, from: "explore" })}
    >
      {body}
    </a>
  );
}

const MAX_STRIP_EVENTS = 30;
const AUTO_SPEED_PX_PER_S = 28; // 읽으면서 따라갈 수 있는 속도
const RESUME_AFTER_MS = 2500; // 손을 뗀 뒤 다시 흐르기까지

/**
 * 가로 목록을 천천히 흘려보낸다. 마우스를 올리거나 · 포커스가 들어가거나 · 손가락이 닿으면 멈추고,
 * 끝에 닿으면 처음으로 돌아간다. '모션 줄이기' 설정에서는 아예 돌지 않는다(버튼과 진행 바만 남는다).
 */
function useAutoScroll(enabled: boolean) {
  // 목록은 데이터가 온 뒤에야 그려진다(그 전엔 스켈레톤). useRef 로 잡으면 첫 effect 때 null 이고 다시 돌지 않아
  // 버튼·진행 바·자동 흐름이 영영 안 나왔다 → 요소를 state 로 받아(callback ref) 붙는 순간 effect 가 돌게 한다.
  const [el, ref] = useState<HTMLUListElement | null>(null);
  const paused = useRef(false);
  const resumeAt = useRef(0);
  const [progress, setProgress] = useState(0);
  const [canScroll, setCanScroll] = useState(false);

  useEffect(() => {
    if (!el) return;
    let frame = 0;
    let last = performance.now();
    let carry = 0; // scrollLeft 는 정수로 반올림된다 → 소수 이동량을 모아서 넘긴다
    const tick = (now: number) => {
      const dt = Math.min(64, now - last);
      last = now;
      const max = el.scrollWidth - el.clientWidth;
      setCanScroll(max > 8);
      setProgress(max > 0 ? el.scrollLeft / max : 0);
      if (enabled && max > 8 && !paused.current && now >= resumeAt.current && document.visibilityState === "visible") {
        carry += (AUTO_SPEED_PX_PER_S * dt) / 1000;
        if (carry >= 1) {
          const step = Math.floor(carry);
          carry -= step;
          if (el.scrollLeft >= max - 1) el.scrollTo({ left: 0, behavior: "smooth" });
          else el.scrollLeft += step;
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [enabled, el]);

  const hold = (on: boolean) => {
    paused.current = on;
    if (!on) resumeAt.current = performance.now() + RESUME_AFTER_MS;
  };
  const page = (direction: -1 | 1) => {
    if (!el) return;
    resumeAt.current = performance.now() + RESUME_AFTER_MS * 2;
    el.scrollBy({ left: direction * Math.max(280, el.clientWidth * 0.8), behavior: "smooth" });
  };
  return { ref, progress, canScroll: el !== null && canScroll, hold, page };
}

export function EventsStrip({ region }: { region?: string }) {
  const range = useMemo(() => {
    const now = new Date();
    return { from: toKstIso(now).slice(0, 10), to: toKstIso(new Date(now.getTime() + 7 * 86_400_000)).slice(0, 10) };
  }, []);
  const events = useEvents({ region, ...range });
  const reduced = useReducedMotion();
  const scroller = useAutoScroll(!reduced);

  return (
    <section aria-labelledby="events-heading" className="bg-grad-soft rounded-[32px] p-5 sm:p-7">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 id="events-heading" className="text-xl font-extrabold tracking-tight text-ink sm:text-2xl">
            이번 주 이벤트
          </h2>
          <p className="text-sm font-bold text-muted-foreground">오늘부터 7일 안에 열리는 축제·전시·공연이에요.</p>
        </div>
        {scroller.canScroll ? (
          <div className="flex shrink-0 gap-1.5">
            <button type="button" onClick={() => scroller.page(-1)} aria-label="이전 이벤트" className="grid size-10 place-items-center rounded-full bg-white text-ink-2 shadow-soft hover:bg-blue-soft hover:text-blue-deep">
              <ChevronLeft aria-hidden className="size-5" />
            </button>
            <button type="button" onClick={() => scroller.page(1)} aria-label="다음 이벤트" className="grid size-10 place-items-center rounded-full bg-white text-ink-2 shadow-soft hover:bg-blue-soft hover:text-blue-deep">
              <ChevronRight aria-hidden className="size-5" />
            </button>
          </div>
        ) : null}
      </div>

      {events.isPending ? (
        <div className="flex gap-3 overflow-hidden" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[132px] w-[260px] shrink-0 rounded-[20px] bg-white/70" />
          ))}
        </div>
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => void events.refetch()} size="sm" />
      ) : events.data.items.length === 0 ? (
        <EmptyState size="sm" mood="think" title="이번 주에는 열리는 이벤트가 없어요" description="다른 지역을 골라 보거나 다음 주에 다시 확인해 주세요." />
      ) : (
        <>
          {/* tabIndex: 키보드만으로도 가로 스크롤 영역을 방향키로 넘길 수 있게. 자동 흐름은 닿는 순간 멈춘다. */}
          <ul
            ref={scroller.ref}
            tabIndex={0}
            onMouseEnter={() => scroller.hold(true)}
            onMouseLeave={() => scroller.hold(false)}
            onFocusCapture={() => scroller.hold(true)}
            onBlurCapture={() => scroller.hold(false)}
            onPointerDown={() => scroller.hold(true)}
            onPointerUp={() => scroller.hold(false)}
            onTouchStart={() => scroller.hold(true)}
            onTouchEnd={() => scroller.hold(false)}
            className="no-scrollbar -mx-1 flex gap-3 overflow-x-auto px-1 py-1 pb-2"
            aria-label="이번 주 이벤트 목록"
          >
            {/* 한 주에 200건이 넘기도 한다 — 가로 띠에는 가까운 것 30건이면 충분하고, 사진도 그만큼만 받는다 */}
            {events.data.items.slice(0, MAX_STRIP_EVENTS).map((event) => (
              <li key={event.id} className="flex">
                <EventCard event={event} />
              </li>
            ))}
          </ul>
          {scroller.canScroll ? (
            <div aria-hidden className="mt-3 h-1 overflow-hidden rounded-full bg-white/70">
              <div className="bg-grad h-full w-1/4 rounded-full" style={{ transform: `translateX(${scroller.progress * 300}%)` }} />
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
