"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as LeafletMap, LayerGroup } from "leaflet";
import "leaflet/dist/leaflet.css";
import { Maximize2 } from "lucide-react";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { minutes, transportLabel } from "@/lib/format";
import { stopColor } from "./colors";
import { escapeHtml, landingClock, layoutLeg, legChipHtml, legsOf, pinHtml, spreadOverlaps, type LatLngTuple, type Pt } from "./map-shared";

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

/**
 * OpenStreetMap 타일 + Leaflet. API 키가 필요 없어 어디서든 바로 뜬다.
 * Leaflet 은 window 를 만지므로 effect 안에서 동적으로 불러온다.
 */
export function LeafletRouteMap({ stops, activeStop, onSelect, route, access, onError }: LeafletRouteMapProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const landingRef = useRef(landingClock());
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

    // 구간마다: 진행 방향 오른쪽으로 비켜 그린 선 · 핀까지의 점선 · 방향/시간 표시 (규칙은 map-shared.ts)
    const toPx = (at: LatLngTuple): Pt => map.latLngToContainerPoint(at);
    const toCoords = (p: Pt) => map.containerPointToLatLng([p.x, p.y]);
    const pinsPx = stops.map((s) => toPx([s.place.lat, s.place.lng]));
    const legs = legsOf(stops, route, (mode, min) => `${transportLabel(mode)} ${minutes(min)}`);
    const layouts = legs.map((leg, i) => layoutLeg(leg.coords.map(toPx), pinsPx[i]!, pinsPx[i + 1]!, pinsPx));
    const stroke = (path: Pt[], weight: number, color: string, dashArray?: string, opacity = 1) =>
      L.polyline(path.map(toCoords), { color, weight, opacity, dashArray, lineCap: "round", lineJoin: "round", interactive: false }).addTo(layer);
    // 흰 테두리를 먼저 모두 깔고 그 위에 색 선을 올린다 → 뒤 구간의 테두리가 앞 구간의 선을 덮지 않는다
    layouts.forEach((layout, i) => {
      if (!legs[i]!.routed) return;
      stroke(layout.line, 11, "#ffffff", undefined, 0.96);
      layout.connectors.forEach((pair) => stroke(pair, 8, "#ffffff", undefined, 0.9));
    });
    layouts.forEach((layout, i) => {
      const color = stopColor(i + 1, stops.length); // 도착 스톱의 색
      stroke(layout.line, 6, color, legs[i]!.routed ? undefined : "1 12"); // 실제 경로가 아니면 점선(곧게 이음)임을 드러낸다
      if (legs[i]!.routed) layout.connectors.forEach((pair) => stroke(pair, 4, color, "1 8"));
      if (layout.chip && legs[i]!.label) {
        L.marker(toCoords(layout.chip), {
          icon: L.divIcon({ className: "", html: legChipHtml(legs[i]!.label, color, layout.chip.angle), iconSize: [0, 0] }),
          interactive: false,
          keyboard: false,
          zIndexOffset: -200,
        }).addTo(layer);
      }
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

    const spread = spreadOverlaps(pinsPx, hostRef.current ? { w: hostRef.current.clientWidth, h: hostRef.current.clientHeight } : undefined);
    const landing = landingRef.current(stops.map((s) => s.place.id).join(","));
    stops.forEach((stop, i) => {
      const active = stop.position === activeStop;
      const fan = spread[i]!;
      const marker = L.marker([stop.place.lat, stop.place.lng], {
        icon: L.divIcon({
          className: "",
          html: pinHtml(stop.position, stop.place.name, stopColor(i, stops.length), active, fan, landing),
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

  // 화면 맞춤: 스톱 + 실제 경로. 길이 크게 돌아가면 선이 화면 밖으로 나갔다 들어와 어디로 가는지 읽을 수 없다.
  // 그렇다고 한없이 축소하지는 않는다 — MIN_FIT_ZOOM 에서 멈춰 번호 핀이 읽히는 크기를 지킨다.
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!L || !map || stops.length === 0) return;
    fitRef.current = () => {
      const pins = L.latLngBounds(stops.map((s) => [s.place.lat, s.place.lng] as LatLngTuple));
      const bounds = L.latLngBounds(stops.map((s) => [s.place.lat, s.place.lng] as LatLngTuple));
      if (route?.source === "osrm") route.coordinates.forEach((at) => bounds.extend(at));
      map.invalidateSize();
      // 위쪽 여백은 핀 높이(56) + 이름표, 아래는 저작권 표기
      const target = map.getBoundsZoom(bounds, false, L.point(140, 170));
      // 핀은 무엇보다 먼저다: 확대 제한은 길이 돌아가서 넓어진 만큼에만 건다. 모든 번호 핀은 언제나 화면 안에 있다
      const pinsZoom = map.getBoundsZoom(pins, false, L.point(140, 170));
      const clamped = Math.max(MIN_FIT_ZOOM, Math.min(MAX_FIT_ZOOM, target));
      const zoom = Math.min(clamped, Math.max(pinsZoom, 1));
      const fitsRoute = zoom <= target;
      map.setView((fitsRoute ? bounds : pins).getCenter(), zoom, { animate: false });
      // 핀은 좌표 위로 55px 솟는다 → 그만큼 시야를 내려, 맨 위 스톱의 핀 머리가 잘리지 않게 한다
      map.panBy([0, -34], { animate: false });
    };
    fitRef.current();
  }, [ready, stops, route]);

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
