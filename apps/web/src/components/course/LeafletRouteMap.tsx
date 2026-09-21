"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap, LayerGroup } from "leaflet";
import "leaflet/dist/leaflet.css";
import { Maximize2 } from "lucide-react";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { stopColor } from "./colors";

interface LeafletRouteMapProps {
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
  /** 실제 보행 경로. 아직 없거나 실패했으면 스톱을 직선으로 잇는다. */
  route?: WalkRoute;
  access?: AccessHint[];
  /** 타일을 하나도 받지 못하면 호출 → 부모가 SVG 약도로 되돌린다 */
  onError: () => void;
}

/**
 * 바탕 지도: OpenStreetMap 표준 타일을 CSS 필터(globals.css 의 .jj-tiles)로 무채색에 가깝게 눌러 쓴다
 * → 구글/카카오 지도처럼 담백해지고, 색이 있는 것은 코스(핀·경로)뿐이 된다. 키가 필요 없고 한글 지명이 나온다.
 * (CARTO Voyager 는 키 없이는 타일에 "API KEY REQUIRED" 워터마크가 찍혀 쓸 수 없었다.)
 * 출시 때는 카카오맵 키(NEXT_PUBLIC_KAKAO_MAP_KEY)를 넣거나, 계약한 타일 주소를 NEXT_PUBLIC_MAP_TILE_URL 로 준다 —
 * OSM 공용 타일 서버는 운영 트래픽용이 아니다.
 */
const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>';
/** 동네 단위 코스가 기본이므로 이보다 멀리서는 보여 주지 않는다 — 번호 핀이 점처럼 작아지는 것을 막는다 */
const MIN_FIT_ZOOM = 15;
const MAX_FIT_ZOOM = 18;

const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

/** 물방울 핀: 끝점이 정확히 좌표를 가리키고, 번호가 지도에서 가장 먼저 읽힌다. 이름표는 아래에 보조로 단다. */
interface Spread {
  dx: number;
  dy: number;
  crowded: boolean;
}

function pinHtml(position: number, name: string, color: string, active: boolean, spread: Spread) {
  const { dx, dy, crowded } = spread;
  const classes = ["jj-pin", active ? "is-active" : "", crowded && !active ? "is-crowded" : ""].filter(Boolean).join(" ");
  const moved = dx !== 0 || dy !== 0;
  // 펼친 핀은 제자리에 점을 남기고 선으로 잇는다 → 번호는 떨어져 있어도 "정확히 어디인지"는 잃지 않는다
  const leader = moved
    ? `<span class="jj-pin-stem" style="width:${Math.hypot(dx, dy).toFixed(1)}px;transform:rotate(${Math.atan2(dy, dx).toFixed(4)}rad)"></span><span class="jj-pin-anchor"></span>`
    : "";
  return `
    <div class="${classes}" style="--pin:${color};--dx:${dx}px;--dy:${dy}px">
      ${leader}
      <span class="jj-pin-drop"><b>${position}</b></span>
      <span class="jj-pin-label">${escapeHtml(name)}</span>
    </div>`;
}

// 핀이 화면에서 차지하는 상자(선택된 핀 58px 기준 + 여유). 두 핀의 상자가 겹치면 "묻힌다".
const PIN_BOX_W = 64;
const PIN_BOX_H = 74;
const FAN_GAP = 74; // 펼쳤을 때 이웃 핀 사이 간격 (핀 너비 46px + 숨 쉴 틈)

/**
 * 겹치는 핀을 항상 펼쳐 둔다(Spiderfy 방식이되, 눌러야 펼쳐지는 게 아니라 상시).
 * 구글맵처럼 덜 중요한 마커를 숨기는 방식은 쓸 수 없다 — 코스는 모든 순번이 보여야 한다.
 * 줌을 당겨 떼는 방식도 한계가 있다: 바로 옆 가게(20m)는 최대 줌에서도 40px 로 핀보다 좁다.
 *
 * 1) 핀 상자가 겹치는 것끼리 무리로 묶고(가로만이 아니라 세로 겹침도 본다)
 * 2) 무리의 중심 위쪽에 순번 순서대로 부채꼴로 놓는다 → 왼쪽부터 1, 2, 3 … 으로 읽힌다.
 */
function spreadOverlaps(points: { x: number; y: number }[]): Spread[] {
  const group = points.map((_, i) => i);
  const find = (i: number): number => (group[i] === i ? i : (group[i] = find(group[i]!)));
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const overlapX = Math.abs(points[i]!.x - points[j]!.x) < PIN_BOX_W;
      const overlapY = Math.abs(points[i]!.y - points[j]!.y) < PIN_BOX_H;
      if (overlapX && overlapY) group[find(j)] = find(i);
    }
  }
  const members = new Map<number, number[]>();
  points.forEach((_, i) => members.set(find(i), [...(members.get(find(i)) ?? []), i]));
  const out: Spread[] = points.map(() => ({ dx: 0, dy: 0, crowded: false }));
  for (const ids of members.values()) {
    if (ids.length < 2) continue;
    const cx = ids.reduce((acc, id) => acc + points[id]!.x, 0) / ids.length;
    const cy = ids.reduce((acc, id) => acc + points[id]!.y, 0) / ids.length;
    // 부채꼴: 핀 사이 호의 길이가 FAN_GAP 이 되도록 반지름을 정한다 (위쪽 ±55° 안에서)
    const span = Math.min((110 * Math.PI) / 180, (ids.length - 1) * 0.72);
    const radius = Math.max(58, (FAN_GAP * (ids.length - 1)) / Math.max(span, 0.01));
    ids.forEach((id, k) => {
      const angle = ids.length === 1 ? 0 : -span / 2 + (span * k) / (ids.length - 1);
      const tx = cx + radius * Math.sin(angle);
      const ty = cy - radius * Math.cos(angle) + radius * 0.55; // 무리 중심 바로 위에 호가 걸치게 조금 내린다
      out[id] = { dx: Math.round(tx - points[id]!.x), dy: Math.round(ty - points[id]!.y), crowded: true };
    });
  }
  return out;
}

type LatLngTuple = [number, number];

/** 한 줄로 온 경로를 스톱에 가장 가까운 꼭짓점에서 끊어 구간별로 나눈다 → 구간마다 도착 스톱의 색으로 칠한다 */
function splitByStops(path: LatLngTuple[], stops: Stop[]): LatLngTuple[][] {
  if (path.length < 2 || stops.length < 2) return [path];
  const cuts: number[] = [0];
  for (let s = 1; s < stops.length - 1; s += 1) {
    const stop = stops[s]!;
    let best = cuts[cuts.length - 1]!;
    let bestD = Infinity;
    for (let i = best; i < path.length; i += 1) {
      const d = (path[i]![0] - stop.place.lat) ** 2 + (path[i]![1] - stop.place.lng) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    cuts.push(best);
  }
  cuts.push(path.length - 1);
  return cuts.slice(1).map((end, i) => path.slice(cuts[i]!, end + 1)).filter((seg) => seg.length > 1);
}

/**
 * OpenStreetMap 타일 + Leaflet. API 키가 필요 없어 어디서든 바로 뜬다.
 * Leaflet 은 window 를 만지므로 effect 안에서 동적으로 불러온다.
 */
export function LeafletRouteMap({ stops, activeStop, onSelect, route, access, onError }: LeafletRouteMapProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const layerRef = useRef<LayerGroup | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const [ready, setReady] = useState(false);
  const [zoomTick, setZoomTick] = useState(0); // 줌이 바뀌면 핀 벌림을 다시 계산한다
  const onSelectRef = useRef(onSelect);
  const onErrorRef = useRef(onError);
  const fitRef = useRef<() => void>(() => undefined);
  onSelectRef.current = onSelect;
  onErrorRef.current = onError;

  // 지도는 한 번만 만든다
  useEffect(() => {
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !hostRef.current || mapRef.current) return;
      leafletRef.current = L;
      const map = L.map(hostRef.current, { zoomControl: false, attributionControl: true, scrollWheelZoom: true, zoomSnap: 0.25 });
      map.attributionControl.setPrefix(false);
      L.control.zoom({ position: "bottomright" }).addTo(map);

      let loaded = 0;
      let failed = 0;
      L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: 19, className: "jj-tiles" })
        .on("tileload", () => (loaded += 1))
        .on("tileerror", () => {
          failed += 1;
          if (loaded === 0 && failed >= 4) onErrorRef.current();
        })
        .addTo(map);

      map.on("click", () => onSelectRef.current(null));
      map.on("zoomend", () => setZoomTick((n) => n + 1));
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
      map.setView([stops[0]?.place.lat ?? 37.5665, stops[0]?.place.lng ?? 126.978], 16);
      // 부모 레이아웃이 자리 잡은 뒤 크기를 다시 잰다
      requestAnimationFrame(() => map.invalidateSize());
      setReady(true);
    });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 초기 중심은 첫 렌더의 스톱으로 충분하다
  }, []);

  // 경로·핀 다시 그리기
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!L || !map || !layer || stops.length === 0) return;
    layer.clearLayers();

    const straight = stops.map((s) => [s.place.lat, s.place.lng] as LatLngTuple);
    const real = route?.source === "osrm" && route.coordinates.length > 1;
    const path = real ? route.coordinates : straight;
    // 흰 테두리를 먼저 깔아 복잡한 지도 위에서도 경로가 또렷하게 뜬다
    L.polyline(path, { color: "#ffffff", weight: 11, opacity: 0.96, lineCap: "round", lineJoin: "round" }).addTo(layer);
    splitByStops(path, stops).forEach((segment, i) => {
      L.polyline(segment, {
        color: stopColor(i + 1, stops.length), // 도착 스톱의 색
        weight: 6,
        opacity: 1,
        lineCap: "round",
        lineJoin: "round",
        dashArray: real ? undefined : "1 12",
      }).addTo(layer);
    });

    // 가까운 지하철 출구 (같은 출구는 한 번만)
    const seen = new Set<string>();
    for (const hint of access ?? []) {
      const s = hint.subway;
      if (!s) continue;
      const key = `${s.lat},${s.lng}`;
      if (seen.has(key)) continue;
      seen.add(key);
      L.marker([s.lat, s.lng], {
        icon: L.divIcon({
          className: "",
          html: `<span class="jj-exit">${escapeHtml(s.station)}${s.exit ? ` ${escapeHtml(s.exit)}번` : ""}</span>`,
          iconSize: [0, 0],
        }),
        interactive: false,
        keyboard: false,
        zIndexOffset: -500,
      }).addTo(layer);
    }

    const spread = spreadOverlaps(stops.map((s) => map.latLngToContainerPoint([s.place.lat, s.place.lng])));
    stops.forEach((stop, i) => {
      const active = stop.position === activeStop;
      const fan = spread[i]!;
      const marker = L.marker([stop.place.lat, stop.place.lng], {
        icon: L.divIcon({
          className: "",
          html: pinHtml(stop.position, stop.place.name, stopColor(i, stops.length), active, fan),
          iconSize: [0, 0],
        }),
        // Leaflet 은 위도(y)로 z 를 정한다 → 순번이 그보다 세게 먹도록 큰 간격을 준다
        zIndexOffset: active ? 100_000 : (stops.length - i) * 5_000,
        title: `${stop.position}. ${stop.place.name}`,
      });
      marker.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        onSelectRef.current(stop.position);
      });
      marker.addTo(layer);
    });
  }, [ready, zoomTick, stops, activeStop, route, access]);

  // 화면 맞춤: **스톱 기준**. 경로 전체에 맞추면 길이 멀리 돌아갈 때 지도가 축소돼 번호가 안 보인다.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map || stops.length === 0) return;
    fitRef.current = () => {
      const bounds = L.latLngBounds(stops.map((s) => [s.place.lat, s.place.lng] as LatLngTuple));
      map.invalidateSize();
      // 위쪽 여백은 핀 높이(56) + 이름표, 아래는 저작권 표기
      const target = map.getBoundsZoom(bounds, false, L.point(140, 170));
      const zoom = Math.max(MIN_FIT_ZOOM, Math.min(MAX_FIT_ZOOM, target));
      map.setView(bounds.getCenter(), zoom, { animate: false });
      // 핀은 좌표 위로 55px 솟는다 → 그만큼 시야를 내려, 맨 위 스톱의 핀 머리가 잘리지 않게 한다
      map.panBy([0, -34], { animate: false });
    };
    fitRef.current();
  }, [ready, stops]);

  useEffect(() => {
    const map = mapRef.current;
    const stop = stops.find((s) => s.position === activeStop);
    if (map && stop && !map.getBounds().pad(-0.18).contains([stop.place.lat, stop.place.lng])) {
      map.panTo([stop.place.lat, stop.place.lng], { animate: true, duration: 0.4 });
    }
  }, [activeStop, stops]);

  return (
    <div className="relative size-full">
      <div
        ref={hostRef}
        className="jj-map size-full"
        role="application"
        aria-label={`코스 지도: ${stops.map((s) => `${s.position}. ${s.place.name}`).join(", ")}`}
      />
      <button
        type="button"
        onClick={() => fitRef.current()}
        className="absolute top-3 right-3 z-[500] inline-flex items-center gap-1.5 rounded-xl bg-white px-3 py-2 text-[13px] font-semibold text-ink-2 shadow-soft hover:bg-soft hover:text-ink"
      >
        <Maximize2 aria-hidden className="size-3.5" />
        코스 전체 보기
      </button>
    </div>
  );
}
