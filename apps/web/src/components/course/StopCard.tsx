"use client";

import { useId, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { BadgeCheck, ChevronDown, ChevronUp, ExternalLink, Eye, History, MapPinned, MessageSquareText, MoreHorizontal, Navigation, Pin, PinOff, RefreshCw, Star, TrendingUp, Users, type LucideIcon } from "lucide-react";
import { track } from "@/lib/analytics";
import { useCategoryImages } from "@/lib/api/hooks";
import type { PlaceSignal, ScoreFeature, Stop, SwapStrategy, Transport } from "@/lib/api/types";
import { clock, minutes, num, roleLabel, transportLabel, won } from "@/lib/format";
import { resolvePlaceImage } from "@/lib/place-image";
import { PlacePhoto } from "@/components/brand/PlacePhoto";
import { ReasonList } from "./ReasonList";
import { cn } from "@/lib/utils";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { DirectionsSheet } from "./DirectionsSheet";
import { SwapSheet } from "./SwapSheet";
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
  /** 후보 목록에서 고른 곳으로 바꾸기 */
  onSwapTo: (placeId: string) => void;
  onMove: (delta: -1 | 1) => void;
  /** 길찾기의 출발지 고르기에 쓰는 코스 전체 · 이동 수단 */
  stops: Stop[];
  transport: Transport;
  /** 고정한 곳(다시 짜도 남는다) */
  pinned?: boolean;
  onTogglePin?: () => void;
  /** 확인할 수 있는 평판 신호 (docs/46): 실측 인기 순위 · 공공 지정 · 영업 신고 30년 · 블로그 후기 수 */
  signals?: PlaceSignal[];
  /** false 면 그 방향으로는 옮길 수 없다 (다른 동네로 넘어가는 경계) */
  canMoveUp?: boolean;
  canMoveDown?: boolean;
}

const SIGNAL_ICON: Record<PlaceSignal["kind"], LucideIcon> = { visited: TrendingUp, designated: BadgeCheck, long_run: History, blog: MessageSquareText };

/** 카드 칩은 짧게: "전주시 완산구에서 사람들이 찾아간 곳 17위" → "완산구 방문 17위" (전체 문장 · 출처는 "자세히") */
function chipLabel(s: PlaceSignal): string {
  if (s.kind !== "visited") return s.label;
  const m = s.label.match(/^(.+?)에서 사람들이 (?:가장 많이 찾아간 곳|찾아간 곳 (\d+)위)$/);
  if (!m) return s.label;
  const area = m[1]!.split(" ").at(-1);
  return `${area} 방문 ${m[2] ?? 1}위`;
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

export function StopCard({ courseId, stop, count, partySize, hiddenFeatures = [], active, swapping, busy, editable = true, onHover, onFocusStop, onSwap, onSwapTo, onMove, stops, transport, pinned = false, onTogglePin, signals = [], canMoveUp = true, canMoveDown = true }: StopCardProps) {
  const reduced = useReducedMotion();
  const [open, setOpen] = useState(false);
  const [street, setStreet] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [directions, setDirections] = useState(false);
  const [swapOpen, setSwapOpen] = useState(false);
  const panelId = useId();
  const { place } = stop;
  // 0원이라고 다 무료는 아니다: 요금 자료가 없는 곳도 0원으로 계산돼 온다 → "무료"는 무료라고 확인된 곳에만 쓴다
  const free = place.is_free === true || (stop.est_price === 0 && place.price_per_person === 0);
  const priceUnknown = !free && stop.est_price === 0;
  // 이 장소에 자료가 없는 항목은 "왜 여기?"에서도 뺀다
  const hidden: ScoreFeature[] = [...hiddenFeatures, ...(place.rating === null ? (["rating"] as const) : []), ...(stop.congestion ? [] : (["congestion"] as const))];
  // 그림 한 장 (docs/43): 서버가 고른 것 — 실제 사진 → 분위기 이미지 → 브랜드 그림
  const image = resolvePlaceImage({ image: place.image, thumbnailUrl: place.thumbnail_url, category: place.category, kind: stop.role, categoryImages: useCategoryImages().data?.items });
  // 같은 상호가 전국에 많다 → 주소의 시·구까지 붙여 검색해야 그 지점이 나온다
  const placeQuery = [place.address?.split(" ").slice(1, 3).join(" "), place.name].filter(Boolean).join(" ");
  const estimated = !free && place.price_is_estimated === true;
  const openSheet = () => {
    setSheet(true);
    track("place_sheet_opened", { course_id: courseId, position: stop.position });
  };

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
        // 상자가 아니라 일정의 한 줄 (docs/31 §6). 지금 보고 있는 곳만 종이 한 장이 깔린다
        "relative rounded-lg px-3 py-4 transition-[background-color,box-shadow] duration-300",
        onFocusStop && "cursor-pointer",
        active ? "bg-white shadow-soft" : "bg-transparent",
      )}
    >
      {/* 기본은 네 가지만 (docs/33 §6): 시각(왼쪽 칸) · 사진 · 장소 · 가격. 나머지는 "자세히"를 눌러야 열린다 */}
      <div className="flex items-start gap-3.5">
        {/* 순번 = 일정 선 위의 점 = 지도의 핀 번호. 누르면 지도에서 이 장소 보기 (키보드로도). 누르는 자리는 44px 로 넓힌다 */}
        <button
          type="button"
          onClick={() => onFocusStop?.(stop.position)}
          aria-label={`지도에서 ${stop.position}번 ${place.name} 보기`}
          className={cn(
            "tabular absolute top-4 -left-[23px] grid size-7 shrink-0 place-items-center rounded-full text-body-sm font-bold text-white ring-4 ring-soft transition-colors duration-300 after:absolute after:-inset-2 after:content-['']",
            active ? "bg-blue-deep" : "bg-ink hover:bg-blue-deep",
          )}
        >
          {stop.position}
        </button>

        {/* 사진은 모든 장소가 같은 크기: 카드 높이가 고르다. 실제 사진이 아니면 "분위기 이미지" 띠나 종류별 그림.
            첫 장소의 사진은 모바일 첫 화면에 보인다 → 먼저 받는다 */}
        <PlacePhoto image={image} sizes="80px" priority={stop.position === 1} className="photo-edge size-[72px] shrink-0 rounded-md sm:size-20" />

        <div className="min-w-0 flex-1">
          <p className="tabular flex items-center gap-2 text-caption font-bold text-tomato-deep">
            {roleLabel(stop.role)}
            {pinned ? (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-tomato-soft px-2 py-0.5 text-tomato-deep">
                <Pin aria-hidden className="size-3" /> 고정됨
              </span>
            ) : null}
            {/* 시각은 일정 왼쪽 칸에 있다. 읽는 사람에게는 여기서도 한 번 */}
            <span className="sr-only">
              , {clock(stop.arrive_at)}부터 {clock(stop.leave_at)}까지
            </span>
          </p>
          <h3 className="line-clamp-2 text-body-lg font-bold break-all">
            {/* 이름을 누르면 우리가 가진 그 가게의 정보(조사된 메뉴 가격 · 사진 · 영업시간 · 개업 연도)를 연다 */}
            {stop.place.kind === "event" ? (
              place.name
            ) : (
              <button type="button" onClick={openSheet} className="max-w-full text-left hover:text-blue-deep hover:underline hover:decoration-2 hover:underline-offset-4">
                {place.name}
              </button>
            )}
          </h3>
          {/* 금액: 이름 아래 한 줄. 평균가로 계산했으면 ≈ 를 붙인다(영수증과 같은 표기) */}
          <p className="tabular mt-1 flex flex-wrap items-baseline gap-x-2">
            {priceUnknown ? (
              <span className="text-body-sm font-semibold text-muted-foreground">가격 정보 없음</span>
            ) : (
              <>
                <span className="money text-price-sm text-ink" title={estimated ? "이 가게의 메뉴판 가격이 아니라, 같은 지역·같은 업종의 1인 평균가로 계산한 금액이에요" : undefined}>
                  {estimated ? <span className="mr-0.5 font-medium text-muted-foreground">≈</span> : null}
                  {free ? "무료" : won(stop.est_price)}
                </span>
                {!free ? (
                  <span className="text-caption font-semibold text-muted-foreground">
                    {partySize > 1 ? (place.price_per_person !== null ? `1인 ${won(place.price_per_person)}` : `${partySize}명 합계`) : "1인"}
                    {estimated ? " · 평균가" : ""}
                  </span>
                ) : null}
              </>
            )}
            {/* 여기까지 오는 이동: "22,000원 · 도보 8분" */}
            {stop.from_prev && stop.position > 1 && stop.from_prev.travel_min > 0 ? (
              <span className="text-caption font-semibold text-muted-foreground">
                · {transportLabel(stop.from_prev.mode)} {minutes(stop.from_prev.travel_min)}
              </span>
            ) : null}
          </p>
          {/* 한 줄 이유: 길게 설명하지 않는다 (자세한 이유는 ⋯ › 자세히 보기) */}
          {stop.reason_short ? <p className="mt-1 line-clamp-1 text-body-sm text-ink-2">{stop.reason_short}</p> : null}
          {/* 사람들 · 공공기관이 말하는 것 (docs/46): 별점이 아니라 출처가 있는 사실만, 카드에는 둘까지 (전부는 "자세히") */}
          {signals.length > 0 ? (
            <ul aria-label="확인된 정보" className="mt-1.5 flex flex-wrap gap-1">
              {signals.slice(0, 2).map((s) => {
                const Icon = SIGNAL_ICON[s.kind];
                return (
                  <li key={s.label} title={`출처: ${s.source}`} className="inline-flex max-w-full items-center gap-1 rounded-full bg-paper-2 px-2 py-0.5 text-caption font-semibold text-ink-2">
                    <Icon aria-hidden className="size-3.5 shrink-0 text-blue-deep" />
                    <span className="truncate">{chipLabel(s)}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      </div>

      {/* 기본 행동은 둘뿐 (docs/42): 길찾기 · 바꾸기. 나머지(자세히 · 지도 · 고정)는 ⋯ 안에 */}
      <div className="mt-2 -mb-1.5 flex items-center justify-end gap-1.5">
        <button
          type="button"
          onClick={() => setDirections(true)}
          aria-label={`${place.name} 길찾기`}
          className="inline-flex h-10 items-center gap-1.5 rounded-full border border-ink/20 bg-white px-3.5 text-body-sm font-semibold text-ink hover:border-ink"
        >
          <Navigation aria-hidden className="size-4" /> 길찾기
        </button>
        {editable ? (
          <button
            type="button"
            onClick={() => setSwapOpen(true)}
            disabled={swapping}
            aria-label={`${place.name} 다른 곳으로 바꾸기`}
            className="inline-flex h-10 items-center gap-1.5 rounded-full border border-ink/20 bg-white px-3.5 text-body-sm font-semibold text-ink hover:border-tomato hover:bg-tomato-soft disabled:opacity-50"
          >
            <RefreshCw aria-hidden className={cn("size-4", swapping && "animate-spin")} /> {swapping ? "바꾸는 중…" : "바꾸기"}
          </button>
        ) : null}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" aria-label={`${place.name} 더보기`} className="grid size-10 place-items-center rounded-full text-ink-2 hover:bg-white hover:text-ink">
              <MoreHorizontal aria-hidden className="size-5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52 rounded-xl p-1.5">
            <DropdownMenuItem
              onSelect={() => {
                if (!open) track("stop_reason_opened", { course_id: courseId, position: stop.position });
                setOpen((v) => !v);
              }}
              aria-controls={panelId}
              className="min-h-11 gap-2 rounded-lg text-body-sm"
            >
              <ChevronDown aria-hidden className={cn("size-4", open && "rotate-180")} /> {open ? "자세히 접기" : "자세히 보기"}
            </DropdownMenuItem>
            {onFocusStop ? (
              <DropdownMenuItem onSelect={() => onFocusStop(stop.position)} className="min-h-11 gap-2 rounded-lg text-body-sm">
                <MapPinned aria-hidden className="size-4" /> 지도에서 보기
              </DropdownMenuItem>
            ) : null}
            {editable && onTogglePin ? (
              <DropdownMenuItem
                onSelect={() => {
                  track("stop_pinned", { course_id: courseId, position: stop.position, pinned: !pinned });
                  onTogglePin();
                }}
                className="min-h-11 gap-2 rounded-lg text-body-sm"
              >
                {pinned ? <PinOff aria-hidden className="size-4" /> : <Pin aria-hidden className="size-4" />} {pinned ? "고정 풀기" : "이 장소 고정"}
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

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
            <div className="mt-3 grid gap-3 border-t border-dashed border-ink/15 pt-3">
              {/* 어디: 업종 · 주소 */}
              <p className="text-body-sm text-ink-2">
                {place.category_name ?? place.category}
                {place.address ? ` · ${place.address}` : ""}
              </p>
              {/* 평점(자료가 있을 때만) · 혼잡도 · 태그는 칩이 아니라 한 줄의 글 (docs/32 B §13) */}
              {place.rating !== null || stop.congestion || place.tags.length > 0 ? (
                <p className="-mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-caption font-semibold text-muted-foreground">
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
                  {place.tags.length > 0 ? <span>{place.tags.slice(0, 3).map((tag) => `#${tag}`).join("  ")}</span> : null}
                </p>
              ) : null}
              {/* 왜 여기: 짠이의 한 줄 → 고른 이유 → 점수 */}
              {stop.reason ? <p className="text-body-sm text-ink">{stop.reason}</p> : null}
              <ReasonList codes={stop.reason_codes} />
              {signals.length > 0 ? (
                <ul aria-label="확인된 정보와 출처" className="grid gap-1 text-caption text-muted-foreground">
                  {signals.map((s) => (
                    <li key={s.label}>
                      <b className="font-semibold text-ink-2">{s.label}</b> · {s.source}
                      {s.url ? (
                        <>
                          {" "}
                          <a href={s.url} target="_blank" rel="noreferrer" className="font-semibold text-blue-deep hover:underline">
                            보기
                          </a>
                        </>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              <ScoreBreakdown scores={stop.score_breakdown} total={stop.score} hidden={hidden} />
              {/* 사진 출처: 실제 사진(한국관광공사 등)이든 분위기 이미지(작가 · 라이선스)든 적는다 */}
              {image.attribution_text ? (
                <a href={image.source_url ?? image.image_url ?? undefined} target="_blank" rel="noreferrer" className="truncate text-caption text-muted-foreground underline-offset-2 hover:underline">
                  {image.attribution_text}
                </a>
              ) : null}

              {/* 두 번째 도구들: 가게 정보 · 거리뷰 · 지도 앱 · 순서 */}
              <div className="flex flex-wrap items-center gap-1.5">
                {stop.place.kind !== "event" ? (
                  <button type="button" onClick={openSheet} className="inline-flex h-9 items-center rounded-full border border-line bg-white px-3 text-body-sm font-semibold text-ink hover:border-ink-2">
                    가게 정보
                  </button>
                ) : null}
                {KAKAO_KEY ? (
                  <button
                    type="button"
                    aria-expanded={street}
                    aria-label={street ? "거리뷰 닫기" : "가게 앞 거리뷰"}
                    onClick={() => {
                      setStreet((v) => !v);
                      if (!street) track("place_link_clicked", { course_id: courseId, position: stop.position, to: "roadview" });
                    }}
                    className={cn("inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-body-sm font-semibold", street ? "border-blue-deep bg-blue-soft text-blue-deep" : "border-line bg-white text-ink hover:border-ink-2")}
                  >
                    <Eye aria-hidden className="size-4" />
                    거리뷰
                  </button>
                ) : null}
                {/* 그 가게의 실제 사진·메뉴판·후기는 지도 앱에 있다(우리가 긁어 올 수는 없다) → 한 번 탭으로 넘긴다. 카카오맵 공식 링크 규격. */}
                <a
                  href={`https://map.kakao.com/link/search/${encodeURIComponent(placeQuery)}`}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="실제 사진·메뉴 보기"
                  onClick={() => track("place_link_clicked", { course_id: courseId, position: stop.position, to: "kakaomap" })}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-body-sm font-semibold text-ink hover:border-ink-2"
                >
                  사진 · 메뉴
                  <ExternalLink aria-hidden className="size-3.5" />
                </a>
                {stop.place.category === STADIUM ? (
                  <a href={KBO_SCHEDULE} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-1 rounded-full bg-blue-soft px-3 text-body-sm font-semibold text-blue-deep hover:brightness-95">
                    오늘 경기 있는지 확인
                    <ExternalLink aria-hidden className="size-3.5" />
                  </a>
                ) : null}
                {editable ? (
                  <span className="ml-auto flex items-center">
                    <button type="button" onClick={() => onMove(-1)} disabled={busy || stop.position === 1 || !canMoveUp} aria-label={`${place.name} 순서를 앞으로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-white disabled:opacity-30">
                      <ChevronUp aria-hidden className="size-4" />
                    </button>
                    <button type="button" onClick={() => onMove(1)} disabled={busy || stop.position === count || !canMoveDown} aria-label={`${place.name} 순서를 뒤로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-white disabled:opacity-30">
                      <ChevronDown aria-hidden className="size-4" />
                    </button>
                  </span>
                ) : null}
              </div>
              {street && KAKAO_KEY ? <RoadviewPeek apiKey={KAKAO_KEY} lat={stop.place.lat} lng={stop.place.lng} name={stop.place.name} /> : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {sheet ? <PlaceSheet place={stop.place} partySize={partySize} onClose={() => setSheet(false)} /> : null}
      {directions ? <DirectionsSheet open onClose={() => setDirections(false)} courseId={courseId} stops={stops} to={stop} mode={transport} /> : null}
      {swapOpen ? (
        <SwapSheet
          open
          onClose={() => setSwapOpen(false)}
          courseId={courseId}
          stop={stop}
          onPick={(placeId) => {
            setSwapOpen(false);
            onSwapTo(placeId);
          }}
          onStrategy={(strategy) => {
            setSwapOpen(false);
            onSwap(strategy);
          }}
        />
      ) : null}
      {swapping ? <span aria-hidden className="skeleton-shimmer absolute inset-0 opacity-60" /> : null}
    </motion.article>
  );
}
