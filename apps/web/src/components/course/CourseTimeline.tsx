"use client";

import { Fragment, useEffect, useRef } from "react";
import { Bus, Car, ExternalLink, Footprints, TrainFront, TramFront, type LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/mascot/EmptyState";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Course, CourseStyle, ScoreFeature, Stop, SwapStrategy, Transport } from "@/lib/api/types";
import { distance, minutes, transportLabel } from "@/lib/format";
import { StopCard } from "./StopCard";

const MODE_ICON: Record<Transport, LucideIcon> = { walk: Footprints, transit: TrainFront, car: Car };
const KAKAO_MODE: Record<Transport, string> = { walk: "walk", transit: "traffic", car: "car" };

interface CourseTimelineProps {
  course: Course;
  /** 코스 스타일. "북적이는 거리" 점수는 재미 우선 코스에서만 쓰인다 */
  style?: CourseStyle;
  partySize: number;
  activeStop: number | null;
  swappingPosition: number | null;
  busy: boolean;
  /** false 면 읽기 전용(친구가 짠 코스): 장소 바꾸기·순서 변경을 숨긴다 */
  editable?: boolean;
  /** 실제 보행 경로. legs[i] 는 stops[i] → stops[i+1] 구간이다. */
  route?: WalkRoute;
  /** stops 와 같은 순서의 가까운 지하철 출구·버스 정류장 */
  access?: AccessHint[];
  onHover: (position: number | null) => void;
  /** 스크롤해서 화면 가운데를 지나는 장소: 지도에서 그 핀을 켠다 (모바일에는 hover 가 없다) */
  onView?: (position: number) => void;
  onSwap: (position: number, strategy: SwapStrategy) => void;
  onMove: (position: number, delta: -1 | 1) => void;
}

/** 카카오맵 공식 링크 규격. 환승·실시간 도착 같은 상세 안내는 지도 앱에 맡긴다. */
function kakaoDirections(mode: Transport, to: Stop, from?: Stop) {
  const point = (s: Stop) => `${encodeURIComponent(s.place.name.replace(/[,/]/g, " "))},${s.place.lat},${s.place.lng}`;
  return from ? `https://map.kakao.com/link/by/${KAKAO_MODE[mode]}/${point(from)}/${point(to)}` : `https://map.kakao.com/link/to/${point(to)}`;
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

export function CourseTimeline({ course, style, partySize, activeStop, swappingPosition, busy, editable = true, route, access, onHover, onView, onSwap, onMove }: CourseTimelineProps) {
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
    <ol ref={listRef} aria-label="코스 일정" className="grid gap-0">
      {course.stops.map((stop, i) => {
        const leg = stop.from_prev;
        const mode = leg?.mode ?? "walk";
        const Icon = MODE_ICON[mode] ?? Footprints;
        // 도보 구간은 실제 길을 따라 잰 값이 있으면 그 값을 보여 준다
        const real = route?.source === "osrm" && mode === "walk" && i > 0 ? route.legs[i - 1] : undefined;
        const travelMin = real?.duration_min ?? leg?.travel_min ?? 0;
        const distanceM = real?.distance_m ?? leg?.distance_m ?? 0;
        const hint = access?.[i];
        return (
          <Fragment key={stop.place.id}>
            {leg ? (
              <li className="py-2 pl-7 text-body-sm text-muted-foreground" aria-label={`${i === 0 ? "출발지에서" : "다음 장소까지"} ${transportLabel(mode)} ${minutes(travelMin)}, ${distance(distanceM)}`}>
                <div className="flex gap-2.5">
                  <span aria-hidden className="w-0 self-stretch border-l-2 border-dashed border-line" />
                  <div className="grid gap-1 py-1">
                    <div className="tabular flex flex-wrap items-center gap-x-2.5 gap-y-1 font-semibold">
                      <Icon aria-hidden className="size-4 text-blue-deep" />
                      <span aria-hidden>
                        {i === 0 ? "출발지에서 " : ""}
                        {leg.hop_to ? `${leg.hop_to}(으)로 ` : ""}
                        {transportLabel(mode)} {minutes(travelMin)} · {distance(distanceM)}
                      </span>
                      <a
                        href={kakaoDirections(mode, stop, course.stops[i - 1])}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-caption font-semibold text-blue-deep hover:bg-blue-soft"
                      >
                        길찾기
                        <ExternalLink aria-hidden className="size-3" />
                      </a>
                    </div>
                    {hint?.subway || hint?.bus ? (
                      <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-caption">
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
            <li>
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
                onSwap={(strategy) => onSwap(stop.position, strategy)}
                onMove={(delta) => onMove(stop.position, delta)}
              />
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
