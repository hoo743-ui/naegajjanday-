"use client";

import { ExternalLink, Map as MapIcon, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CourseRoute, Stop, Transport } from "@/lib/api/types";
import { distance, minutes, transportLabel } from "@/lib/format";
import { naverWebDirections, openInNaverMap, type MapPoint } from "@/lib/naver-map";

const MAX_VIA = 5;
const point = (s: Stop): MapPoint => ({ lat: s.place.lat, lng: s.place.lng, name: s.place.name });

interface RoutePanelProps {
  stops: Stop[];
  transport: Transport;
  route?: CourseRoute;
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  /** 지금 보고 있는 장소 — 네이버 길찾기의 출발점 (없으면 첫 장소) */
  activeStop: number | null;
  onShowAll: () => void;
}

/**
 * 이동 (docs/27 §11 · §13 · §14): 오늘의 동선을 한 줄로 — 총 이동 시간 · 거리 · 무엇으로 쟀는지.
 * [전체 코스 지도에서 보기]는 핀 · 경로 · 순서 · 이동 시간이 모두 보이게 지도를 맞추고,
 * [네이버 지도에서 길찾기]는 보고 있는 장소에서 다음 장소로(자동차는 남은 곳을 경유지로) 넘긴다. 이 화면은 그대로 남는다.
 */
export function RoutePanel({ stops, transport, route, loading, failed, onRetry, activeStop, onShowAll }: RoutePanelProps) {
  // 마지막 장소를 보고 있으면 "다음"이 없다 → 바로 앞 장소에서 그곳으로 가는 길을 넘긴다
  const fromIndex = Math.max(0, Math.min(stops.findIndex((s) => s.position === activeStop), stops.length - 2));
  const from = stops[fromIndex];
  const to = transport === "car" ? stops[stops.length - 1] : stops[fromIndex + 1];
  const via = transport === "car" ? stops.slice(fromIndex + 1, -1).slice(0, MAX_VIA) : [];
  const measured = route?.legs.filter((l) => l.source === "naver" || l.source === "osrm").length ?? 0;
  const estimated = route?.legs.filter((l) => l.source === "estimate").length ?? 0;
  const source =
    !route || route.legs.length === 0
      ? null
      : estimated === 0
        ? route.legs.some((l) => l.source === "naver")
          ? "네이버 지도로 잰 실제 경로예요"
          : "실제 길을 따라 잰 시간이에요"
        : measured === 0
          ? "직선 거리로 어림한 시간이에요. 정확한 시간은 네이버 지도에서 확인하세요"
          : "일부 구간은 직선 거리로 어림했어요";

  return (
    <section aria-labelledby="route-panel" className="rule-section gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="route-panel" className="text-body font-bold text-ink">
          오늘의 이동
        </h2>
        {route ? (
          <p className="tabular text-body-sm text-ink-2">
            {transportLabel(transport)} 이동 <b className="font-bold text-ink">{minutes(route.totals.travel_min)}</b> · {distance(route.totals.distance_m)}
          </p>
        ) : null}
      </div>
      <div aria-live="polite" className="text-body-sm text-muted-foreground">
        {loading ? (
          <p className="skeleton-shimmer h-5 w-40 rounded-md" aria-label="경로를 계산하는 중" />
        ) : failed ? (
          <p className="flex flex-wrap items-center gap-2">
            경로를 계산하지 못했어요. 지도에는 장소 사이를 곧게 이어 두었어요.
            <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold text-blue-deep hover:bg-blue-soft">
              <RotateCw aria-hidden className="size-3.5" /> 다시 시도
            </button>
          </p>
        ) : source ? (
          <p>{source}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="soft" size="md" className="bg-white" onClick={onShowAll}>
          <MapIcon aria-hidden /> 전체 코스 지도에서 보기
        </Button>
        {from && to && from !== to ? (
          <Button asChild variant="soft" size="md" className="bg-white">
            <a href={naverWebDirections(point(from), point(to), transport, via.map(point))} target="_blank" rel="noreferrer" onClick={(e) => openInNaverMap(e, point(from), point(to), transport, via.map(point))}>
              네이버 지도에서 길찾기 <ExternalLink aria-hidden />
            </a>
          </Button>
        ) : null}
      </div>
      {from && to && from !== to ? (
        <p className="text-caption text-muted-foreground">
          {from.position}. {from.place.name} → {to.position}. {to.place.name}
          {via.length > 0 ? ` (경유 ${via.length}곳)` : ""} · 네이버 지도가 새 창에서 열려요
        </p>
      ) : null}
    </section>
  );
}
