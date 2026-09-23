"use client";

import { Fragment, useEffect, useRef } from "react";
import { Bus, Car, Footprints, TrainFront, TramFront, type LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/mascot/EmptyState";
import type { AccessHint } from "@/lib/api/hooks";
import type { Course, CourseRoute, CourseStyle, ScoreFeature, Stop, SwapStrategy, Transport } from "@/lib/api/types";
import { clock, distance, minutes, transportLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StopCard } from "./StopCard";

const MODE_ICON: Record<Transport, LucideIcon> = { walk: Footprints, transit: TrainFront, car: Car };

interface CourseTimelineProps {
  course: Course;
  /** 이동 수단: 역 출구 · 정류장 안내는 대중교통 코스에서만 모든 구간에 (걷는 코스는 출발 구간만) */
  transport?: Transport;
  /** 코스 스타일. "북적이는 거리" 점수는 재미 우선 코스에서만 쓰인다 */
  style?: CourseStyle;
  partySize: number;
  activeStop: number | null;
  swappingPosition: number | null;
  busy: boolean;
  /** false 면 읽기 전용(친구가 짠 코스): 장소 바꾸기·순서 변경을 숨긴다 */
  editable?: boolean;
  /** 코스 경로(docs/27). legs 의 to_seq 가 그 구간이 도착하는 장소다. 없으면(계산 중 · 실패) 엔진의 추정값을 쓴다 */
  route?: CourseRoute;
  /** stops 와 같은 순서의 가까운 지하철 출구·버스 정류장 */
  access?: AccessHint[];
  onHover: (position: number | null) => void;
  /** 스크롤해서 화면 가운데를 지나는 장소: 지도에서 그 핀을 켠다 (모바일에는 hover 가 없다) */
  onView?: (position: number) => void;
  /** 카드를 누르면: 지도가 그 장소로 옮겨 가 확대하고, 그 장소로 오는 구간을 강조한다 */
  onFocusStop?: (position: number) => void;
  onSwap: (position: number, strategy: SwapStrategy) => void;
  onSwapTo: (position: number, placeId: string) => void;
  onMove: (position: number, delta: -1 | 1) => void;
  /** 고정한 장소 id (다시 짜도 남는다) */
  pins?: string[];
  onTogglePin?: (placeId: string) => void;
}


/**
 * 코스 전체에서 자료가 없는 점수 항목. 리뷰·혼잡도 자료가 없으면 엔진은 모든 장소에 같은 중립값을 넣는다
 * → 모든 장소의 값이 같으면 "본 것"이 아니므로 막대를 그리지 않는다.
 */
function featuresWithoutSignal(stops: Stop[], style?: CourseStyle): ScoreFeature[] {
  const flat = (key: ScoreFeature) => stops.every((s) => (s.score_breakdown[key] ?? 0) === (stops[0]?.score_breakdown[key] ?? 0));
  const hidden: ScoreFeature[] = [];
  // 평점 자료도 아직 없다: 모든 장소가 같은 중립값이면 "평점이 강점"이라고 그리지 않는다
  if (flat("rating")) hidden.push("rating");
  if (flat("sentiment")) hidden.push("sentiment");
  if (flat("congestion")) hidden.push("congestion");
  if (style !== "fun" && stops.every((s) => !s.score_breakdown.buzz)) hidden.push("buzz");
  return hidden;
}

export function CourseTimeline({ course, transport, style, partySize, activeStop, swappingPosition, busy, editable = true, route, access, onHover, onView, onFocusStop, onSwap, onSwapTo, onMove, pins = [], onTogglePin }: CourseTimelineProps) {
  const listRef = useRef<HTMLOListElement>(null);
  const onViewRef = useRef(onView);
  useEffect(() => {
    onViewRef.current = onView;
  }, [onView]);

  // 보고 있는 장소 = 화면 높이의 50~60% 띠를 지나는 카드. 모바일은 위쪽 절반이 지도라, 카드가 읽히는 자리가 이 띠다
  useEffect(() => {
    const list = listRef.current;
    if (!list || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) onViewRef.current?.(Number((entry.target as HTMLElement).dataset.position));
        }
      },
      { rootMargin: "-50% 0px -40% 0px" },
    );
    list.querySelectorAll<HTMLElement>("article[data-position]").forEach((card) => observer.observe(card));
    return () => observer.disconnect();
  }, [course.stops]);

  if (course.stops.length === 0) {
    return (
      <EmptyState
        mood="sorry"
        title="이 조건으로는 갈 곳을 찾지 못했어요"
        description="예산을 조금 올리거나 다른 지역으로 다시 짜 볼까요?"
      />
    );
  }

  const noSignal = featuresWithoutSignal(course.stops, style);

  return (
    // 하루의 흐름 (docs/31 §2): 왼쪽 칸은 시각, 가운데 점선은 이동, 오른쪽은 할 일. 장소의 순번이 선 위의 점이다
    <ol ref={listRef} aria-label="코스 일정" className="grid gap-0">
      {course.stops.map((stop, i) => {
        const leg = stop.from_prev;
        const mode = leg?.mode ?? "walk";
        const Icon = MODE_ICON[mode] ?? Footprints;
        // 장소 사이의 구간은 경로 API 의 값을 쓴다: 실측(네이버 · 보행 라우터) · 추정(엔진) · 계산 못 함을 구분해서 말한다
        const measured = i > 0 ? route?.legs.find((l) => l.to_seq === stop.position) : undefined;
        const unavailable = measured?.source === "unavailable";
        const estimated = !measured || measured.source === "estimate";
        const travelMin = measured?.duration_min ?? leg?.travel_min ?? 0;
        const distanceM = measured?.distance_m ?? leg?.distance_m ?? 0;
        const hint = access?.[i];

        return (
          <Fragment key={stop.place.id}>
            {/* 출발점이 곧 첫 장소면(대학교 · 장소를 중심으로 짠 하루) "출발지에서 0분 · 0m" 줄은 말할 것이 없다 */}
            {leg && !(i === 0 && distanceM < 30) ? (
              <li
                className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-5 text-body-sm text-muted-foreground"
                aria-label={unavailable ? "다음 장소까지 경로 정보를 불러오지 못했어요" : `${i === 0 ? "출발지에서" : "다음 장소까지"} ${transportLabel(mode)} ${estimated ? "약 " : ""}${minutes(travelMin)}, ${distance(distanceM)}${estimated && i > 0 ? " (추정)" : ""}`}
              >
                <span aria-hidden />
                <div className="border-l-2 border-dashed border-ink/20 py-1.5 pl-5">
                  <div className="grid gap-1 py-1">
                    <div className="tabular flex flex-wrap items-center gap-x-2.5 gap-y-1 font-semibold">
                      <Icon aria-hidden className="size-4 text-blue-deep" />
                      {unavailable ? (
                        <span aria-hidden>경로 정보를 불러오지 못했어요</span>
                      ) : (
                        // 실제 길을 재지 못한 구간은 "약"으로 밝힌다 (대중교통 · 자동차 키 없음 · 라우터 실패) — 배지는 두지 않는다 (docs/33)
                        <span aria-hidden title={estimated && i > 0 ? "실제 길을 재지 못해 직선 거리로 어림한 값이에요. 정확한 시간은 네이버 지도에서 확인하세요." : undefined}>
                          {i === 0 ? "출발지에서 " : ""}
                          {leg.hop_to ? `${leg.hop_to}(으)로 ` : ""}
                          {transportLabel(mode)} {estimated && i > 0 ? "약 " : ""}
                          {minutes(travelMin)} · {distance(distanceM)}
                        </span>
                      )}
                    </div>
                    {(transport === "transit" || i === 0) && (hint?.subway || hint?.bus) ? (
                      // 걷는 코스의 출발 구간 안내는 넓은 화면에서만: 모바일 첫 화면에 첫 장소가 들어오게
                      <p className={cn("flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption", transport !== "transit" && "max-sm:hidden")}>
                        {hint.subway ? (
                          <span className="inline-flex items-center gap-1">
                            <TramFront aria-hidden className="size-3.5 text-success" />
                            <span>
                              <b className="font-semibold text-ink-2">
                                {hint.subway.station}
                                {hint.subway.exit ? ` ${hint.subway.exit}번 출구` : ""}
                              </b>
                              에서 도보 {minutes(hint.subway.walk_min)}
                            </span>
                          </span>
                        ) : null}
                        {hint.bus ? (
                          <span className="inline-flex items-center gap-1">
                            <Bus aria-hidden className="size-3.5 text-blue-deep" />
                            <span>
                              <b className="font-semibold text-ink-2">{hint.bus.name}</b> 정류장 도보 {minutes(hint.bus.walk_min)}
                            </span>
                          </span>
                        ) : null}
                      </p>
                    ) : null}
                  </div>
                </div>
              </li>
            ) : null}
            <li className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-5">
              <p aria-hidden className="tabular pt-[18px] text-right leading-tight">
                <span className="block text-body font-bold text-ink">{clock(stop.arrive_at)}</span>
                <span className="text-caption text-muted-foreground">{clock(stop.leave_at)}</span>
              </p>
              <div className="border-l-2 border-dashed border-ink/20 pl-2">
              <StopCard
                courseId={course.id}
                stop={stop}
                count={course.stops.length}
                partySize={partySize}
                hiddenFeatures={noSignal}
                active={activeStop === stop.position}
                swapping={swappingPosition === stop.position}
                busy={busy}
                editable={editable}
                // 여러 동네를 잇는 코스: 순서는 그 동네 안에서만 바꾼다 (동네 경계를 넘기면 "○○(으)로 이동" 구간이 어긋난다)
                canMoveUp={!leg?.hop_to}
                canMoveDown={!course.stops[i + 1]?.from_prev?.hop_to}
                onHover={onHover}
                onFocusStop={onFocusStop}
                onSwap={(strategy) => onSwap(stop.position, strategy)}
                onSwapTo={(placeId) => onSwapTo(stop.position, placeId)}
                stops={course.stops}
                transport={transport ?? "walk"}
                pinned={pins.includes(stop.place.id)}
                onTogglePin={onTogglePin ? () => onTogglePin(stop.place.id) : undefined}
                onMove={(delta) => onMove(stop.position, delta)}
              />
              </div>
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
