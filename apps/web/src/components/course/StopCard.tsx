"use client";

import { useId, useState } from "react";
import Image from "next/image";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ChevronDown, ChevronUp, Clock, ExternalLink, Eye, Star, Users } from "lucide-react";
import { track } from "@/lib/analytics";
import { categoryImageFor, useCategoryImages } from "@/lib/api/hooks";
import type { ScoreFeature, Stop, SwapStrategy } from "@/lib/api/types";
import { clock, num, roleLabel, won } from "@/lib/format";
import { canOptimize, photoCredit } from "@/lib/photo-credit";
import { ReasonList } from "./ReasonList";
import { cn } from "@/lib/utils";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { SwapMenu } from "./SwapMenu";
import { PlaceSheet } from "./PlaceSheet";
import { RoadviewPeek } from "./RoadviewPeek";

interface StopCardProps {
  courseId: string;
  stop: Stop;
  count: number;
  partySize: number;
  /** 코스 전체에 자료가 없는 점수 항목 (CourseTimeline 이 계산) */
  hiddenFeatures?: readonly ScoreFeature[];
  active: boolean;
  swapping: boolean;
  busy: boolean;
  /** false 면(친구가 짠 코스) 순서 변경·바꾸기 버튼을 아예 그리지 않는다 — 눌러도 403 인 버튼을 두지 않는다 */
  editable?: boolean;
  onHover: (position: number | null) => void;
  /** 카드(버튼 · 링크가 아닌 곳)나 순번을 누르면: 지도가 이 장소로 옮겨 가 확대한다 (docs/27 §9) */
  onFocusStop?: (position: number) => void;
  onSwap: (strategy: SwapStrategy) => void;
  onMove: (delta: -1 | 1) => void;
  /** false 면 그 방향으로는 옮길 수 없다 (다른 동네로 넘어가는 경계) */
  canMoveUp?: boolean;
  canMoveDown?: boolean;
}

/** 혼잡도 value(0~1, 높을수록 붐빔) → 배지 색. 문구(level)는 API 가 준 그대로 쓴다. */
function congestionTone(value: number) {
  if (value < 0.35) return "bg-success-soft text-success";
  if (value < 0.6) return "bg-paper-2 text-ink-2";
  return "bg-pink-soft text-pink-deep";
}

/** 야구장은 경기가 있는 날에만 의미가 있다. 경기 일정은 공식 오픈 데이터가 없어 우리가 알 수 없으므로 KBO 공식 일정으로 보낸다. */
const STADIUM = "activity.stadium";
const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;
const KBO_SCHEDULE = "https://www.koreabaseball.com/schedule/schedule.aspx";

export function StopCard({ courseId, stop, count, partySize, hiddenFeatures = [], active, swapping, busy, editable = true, onHover, onFocusStop, onSwap, onMove, canMoveUp = true, canMoveDown = true }: StopCardProps) {
  const reduced = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [street, setStreet] = useState(false);
  const [sheet, setSheet] = useState(false);
  const panelId = useId();
  const { place } = stop;
  // 0원이라고 다 무료는 아니다: 요금 자료가 없는 곳도 0원으로 계산돼 온다 → "무료"는 무료라고 확인된 곳에만 쓴다
  const free = place.is_free === true || (stop.est_price === 0 && place.price_per_person === 0);
  const priceUnknown = !free && stop.est_price === 0;
  // 이 장소에 자료가 없는 항목은 "왜 여기?"에서도 뺀다
  const hidden: ScoreFeature[] = [...hiddenFeatures, ...(place.rating === null ? (["rating"] as const) : []), ...(stop.congestion ? [] : (["congestion"] as const))];
  const example = categoryImageFor(useCategoryImages().data?.items, place.category);
  const credit = photoCredit(place.thumbnail_url);
  // 같은 상호가 전국에 많다 → 주소의 시·구까지 붙여 검색해야 그 지점이 나온다
  const placeQuery = [place.address?.split(" ").slice(1, 3).join(" "), place.name].filter(Boolean).join(" ");

  return (
    <motion.article
      layout={reduced ? false : "position"}
      data-position={stop.position}
      onMouseEnter={() => onHover(stop.position)}
      onMouseLeave={() => onHover(null)}
      onFocusCapture={() => onHover(stop.position)}
      onClick={(e) => {
        // 카드 안의 버튼 · 링크(바꾸기 · 순서 · 거리뷰 · 지도 앱 …)는 자기 일만 한다
        if ((e.target as HTMLElement).closest("a, button, input, select, textarea, [role='button'], [role='menu'], [role='dialog']")) return;
        onFocusStop?.(stop.position);
      }}
      aria-label={`${stop.position}번째 ${roleLabel(stop.role)}: ${place.name}`}
      aria-busy={swapping}
      className={cn(
        "relative overflow-hidden rounded-card border bg-white p-4 shadow-soft transition-[box-shadow,border-color] duration-300 sm:p-5",
        onFocusStop && "cursor-pointer",
        active ? "border-blue-deep/70 shadow-card ring-2 ring-blue-deep/15" : "border-transparent",
      )}
    >
      {/* 그 가게의 실제 사진이면 크게 보여 준다: "실제로 있는 곳"이라는 믿음이 여기서 생긴다.
          업종 예시 사진은 아래 줄의 작은 썸네일로만 쓴다(같은 라떼 사진이 코스마다 화면을 덮지 않게). */}
      {place.thumbnail_url ? (
        <div className="photo-edge relative -mx-4 -mt-4 mb-4 aspect-[16/9] overflow-hidden sm:-mx-5 sm:-mt-5">
          {/* 첫 장소의 사진은 모바일 첫 화면에서 가장 큰 이미지다 → 먼저 받는다 */}
          <Image priority={stop.position === 1} src={place.thumbnail_url} alt="" fill sizes="(max-width: 1024px) 100vw, 520px" className="object-cover" unoptimized={!canOptimize(place.thumbnail_url)} />
          <span aria-hidden className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-black/40 to-transparent" />
          {credit ? <span className="absolute right-2.5 bottom-2 rounded-md bg-black/45 px-1.5 py-0.5 text-caption font-medium text-white/95">{credit}</span> : null}
        </div>
      ) : null}

      <div className="flex items-start gap-3.5">
        {/* 순번 = 지도에서 이 장소 보기 (키보드로도 카드 → 지도 연동을 쓸 수 있게). 누르는 자리는 44px 로 넓힌다 */}
        <button
          type="button"
          onClick={() => onFocusStop?.(stop.position)}
          aria-label={`지도에서 ${stop.position}번 ${place.name} 보기`}
          className={cn(
            "tabular relative mt-0.5 grid size-8 shrink-0 place-items-center rounded-full text-body-sm font-bold text-white transition-colors duration-300 after:absolute after:-inset-1.5 after:content-['']",
            active ? "bg-blue-deep" : "bg-ink hover:bg-blue-deep",
          )}
        >
          {stop.position}
        </button>

        <div className="min-w-0 flex-1">
          <p className="tabular flex flex-wrap items-center gap-x-2 text-caption font-extrabold text-blue-deep">
            <span>{roleLabel(stop.role)}</span>
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Clock aria-hidden className="size-3" />
              {clock(stop.arrive_at)} – {clock(stop.leave_at)}
            </span>
          </p>
          <h3 className="truncate text-body-lg font-semibold">
            {/* 이름을 누르면 우리가 가진 그 가게의 정보(조사된 메뉴 가격 · 사진 · 영업시간 · 개업 연도)를 연다 */}
            {stop.place.kind === "event" ? (
              place.name
            ) : (
              <button type="button" onClick={() => { setSheet(true); track("place_sheet_opened", { course_id: courseId, position: stop.position }); }} className="max-w-full truncate text-left underline decoration-line decoration-2 underline-offset-4 hover:decoration-blue-deep">
                {place.name}
              </button>
            )}
          </h3>
          <p className="truncate text-body-sm text-muted-foreground">
            {place.category_name ?? place.category}
            {place.address ? ` · ${place.address}` : ""}
          </p>
        </div>

        {/* 금액: 카드에서 가장 큰 글자 */}
        <p className="money shrink-0 text-right text-price-sm">
          {priceUnknown ? (
            <span className="text-body-sm font-semibold text-muted-foreground">가격 정보 없음</span>
          ) : (
            <>
              {free ? "0원" : won(stop.est_price)}
              <small className="mt-0.5 block text-caption font-semibold tracking-normal text-muted-foreground">
                {free ? "무료" : partySize > 1 ? (place.price_per_person !== null ? `1인 ${won(place.price_per_person)}` : `${partySize}명 합계`) : "1인"}
              </small>
              {!free && place.price_is_estimated ? (
                <span className="mt-1 inline-block rounded-md bg-gold-soft px-1.5 py-0.5 text-caption font-semibold tracking-normal text-gold-ink" title="이 가게의 메뉴판 가격이 아니라, 같은 지역·같은 업종의 1인 평균가로 계산한 금액이에요">
                  평균가
                </span>
              ) : null}
            </>
          )}
        </p>
      </div>

      {place.rating !== null || stop.congestion || place.tags.length > 0 || (!place.thumbnail_url && example) ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-caption font-semibold">
          {!place.thumbnail_url && example ? (
            // 그 가게의 실제 사진이 아니라 업종 대표 이미지임을 밝히고, 오픈 라이선스 조건대로 출처를 단다
            <a
              href={example.page_url ?? example.url}
              target="_blank"
              rel="noreferrer"
              title="이 가게의 사진이 아니라 같은 업종의 예시 사진이에요"
              className="mr-1 inline-flex items-center gap-2 rounded-full border border-line py-0.5 pr-2.5 pl-0.5 font-medium text-muted-foreground hover:border-ink-2"
            >
              <span className="relative size-7 shrink-0 overflow-hidden rounded-full">
                <Image src={example.url} alt="" fill sizes="28px" className="object-cover" unoptimized={!canOptimize(example.url)} />
              </span>
              <span className="max-w-[210px] truncate text-caption">
                예시 사진 · © {example.author} · {example.license}
              </span>
            </a>
          ) : null}
          {place.rating !== null ? (
            <span className="tabular inline-flex items-center gap-1 text-ink-2">
              <Star aria-hidden className="size-3.5 fill-gold text-gold-deep" />
              <span className="sr-only">평점</span>
              {place.rating.toFixed(1)}
              <span className="font-medium text-muted-foreground">({num(place.review_count)})</span>
            </span>
          ) : null}
          {stop.congestion ? (
            <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5", congestionTone(stop.congestion.value))}>
              <Users aria-hidden className="size-3" />
              <span className="sr-only">도착 시간 혼잡도</span>
              {stop.congestion.level}
            </span>
          ) : null}
          {place.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="rounded-full bg-soft px-2 py-0.5 text-ink-2">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {/* 이유는 상자가 아니라 본문이다: 왼쪽의 가는 선 하나로 "짠이의 말"임을 표시한다 */}
      {stop.reason ? <p className="mt-3 border-l-2 border-line pl-3 text-body-sm font-medium text-ink-2">{stop.reason}</p> : null}

      {/* 도구는 한 줄: 왼쪽은 읽을 것(왜 여기 · 거리뷰 · 지도 앱), 오른쪽은 바꿀 것(순서 · 바꾸기) */}
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-2.5">
        <div className="flex min-w-0 items-center gap-0.5">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => {
              if (!open) track("stop_reason_opened", { course_id: courseId, position: stop.position });
              setOpen((v) => !v);
            }}
            className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-1.5 text-body-sm font-semibold text-blue-deep hover:bg-blue-soft"
          >
            왜 여기?
            <ChevronDown aria-hidden className={cn("size-4 transition-transform duration-300", open && "rotate-180")} />
          </button>
          {KAKAO_KEY ? (
            <button
              type="button"
              aria-expanded={street}
              aria-label={street ? "거리뷰 닫기" : "가게 앞 거리뷰"}
              title={street ? "거리뷰 닫기" : "가게 앞 거리뷰"}
              onClick={() => {
                setStreet((v) => !v);
                if (!street) track("place_link_clicked", { course_id: courseId, position: stop.position, to: "roadview" });
              }}
              className={cn("grid size-11 place-items-center rounded-full hover:bg-soft", street ? "bg-blue-soft text-blue-deep" : "text-ink-2 hover:text-ink")}
            >
              <Eye aria-hidden className="size-4" />
            </button>
          ) : null}
          {/* 그 가게의 실제 사진·메뉴판·후기는 지도 앱에 있다(우리가 긁어 올 수는 없다) → 한 번 탭으로 넘긴다. 카카오맵 공식 링크 규격. */}
          <a
            href={`https://map.kakao.com/link/search/${encodeURIComponent(placeQuery)}`}
            target="_blank"
            rel="noreferrer"
            aria-label="실제 사진·메뉴 보기"
            title="지도 앱에서 실제 사진 · 메뉴 보기"
            onClick={() => track("place_link_clicked", { course_id: courseId, position: stop.position, to: "kakaomap" })}
            className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft hover:text-ink"
          >
            <ExternalLink aria-hidden className="size-4" />
          </a>
          {stop.place.category === STADIUM ? (
            <a
              href={KBO_SCHEDULE}
              target="_blank"
              rel="noreferrer"
              className="ml-1 inline-flex items-center gap-1 rounded-full bg-blue-soft px-2.5 py-1.5 text-body-sm font-semibold text-blue-deep hover:brightness-95"
            >
              오늘 경기 있는지 확인
              <ExternalLink aria-hidden className="size-3.5" />
            </a>
          ) : null}
        </div>
        {editable ? (
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={() => onMove(-1)} disabled={busy || stop.position === 1 || !canMoveUp} aria-label={`${place.name} 순서를 앞으로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft disabled:opacity-30">
              <ChevronUp aria-hidden className="size-4" />
            </button>
            <button type="button" onClick={() => onMove(1)} disabled={busy || stop.position === count || !canMoveDown} aria-label={`${place.name} 순서를 뒤로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft disabled:opacity-30">
              <ChevronDown aria-hidden className="size-4" />
            </button>
            <SwapMenu placeName={place.name} pending={swapping} onSwap={onSwap} />
          </div>
        ) : null}
      </div>

      {street && KAKAO_KEY ? <RoadviewPeek apiKey={KAKAO_KEY} lat={stop.place.lat} lng={stop.place.lng} name={stop.place.name} /> : null}

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={panelId}
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.2, 0.8, 0.2, 1] }}
            className="overflow-hidden"
          >
            <ReasonList codes={stop.reason_codes} className="mt-3" />
            <ScoreBreakdown scores={stop.score_breakdown} total={stop.score} hidden={hidden} className="mt-3" />
          </motion.div>
        ) : null}
      </AnimatePresence>

      {sheet ? <PlaceSheet place={stop.place} partySize={partySize} onClose={() => setSheet(false)} /> : null}
      {swapping ? <span aria-hidden className="skeleton-shimmer absolute inset-0 opacity-60" /> : null}
    </motion.article>
  );
}
