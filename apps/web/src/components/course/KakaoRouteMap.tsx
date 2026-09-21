"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2 } from "lucide-react";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { stopColor } from "./colors";
import { escapeHtml, pinHtml, splitByStops, spreadOverlaps, type LatLngTuple } from "./map-shared";

// ── Kakao Maps JS SDK (쓰는 만큼만 타입 선언) ─────────────────
interface KLatLng {
  getLat(): number;
  getLng(): number;
}
interface KPoint {
  x: number;
  y: number;
}
interface KBounds {
  extend(point: KLatLng): void;
  contain(point: KLatLng): boolean;
}
interface KMap {
  setBounds(bounds: KBounds, top?: number, right?: number, bottom?: number, left?: number): void;
  getBounds(): KBounds;
  getLevel(): number;
  setLevel(level: number): void;
  panBy(dx: number, dy: number): void;
  panTo(point: KLatLng): void;
  relayout(): void;
  getProjection(): { containerPointFromCoords(point: KLatLng): KPoint };
  addControl(control: unknown, position: unknown): void;
}
interface KOverlay {
  setMap(map: KMap | null): void;
}
interface KakaoMaps {
  load(callback: () => void): void;
  LatLng: new (lat: number, lng: number) => KLatLng;
  LatLngBounds: new () => KBounds;
  Map: new (container: HTMLElement, options: { center: KLatLng; level: number }) => KMap;
  CustomOverlay: new (options: { position: KLatLng; content: HTMLElement; xAnchor?: number; yAnchor?: number; zIndex?: number; clickable?: boolean }) => KOverlay;
  Polyline: new (options: { path: KLatLng[]; strokeWeight: number; strokeColor: string; strokeOpacity: number; strokeStyle: string }) => KOverlay;
  ZoomControl: new () => unknown;
  ControlPosition: { BOTTOMRIGHT: unknown };
  event: { addListener(target: KMap, type: string, handler: () => void): void; removeListener(target: KMap, type: string, handler: () => void): void };
}
/** 전역 Window 타입을 넓히지 않고 여기서만 읽는다 (SDK 는 이 파일만 쓴다) */
const kakaoMaps = (): KakaoMaps | undefined => (window as unknown as { kakao?: { maps: KakaoMaps } }).kakao?.maps;

/** 동네 단위 코스가 기본: 이보다 멀리서는 보여 주지 않는다(카카오는 숫자가 작을수록 가깝다). Leaflet 의 MIN_FIT_ZOOM=15 와 같은 거리감. */
const MAX_FIT_LEVEL = 4;

let sdkPromise: Promise<KakaoMaps> | null = null;

function loadKakao(key: string): Promise<KakaoMaps> {
  sdkPromise ??= new Promise<KakaoMaps>((resolve, reject) => {
    const ready = () => {
      const maps = kakaoMaps();
      if (!maps) return reject(new Error("kakao sdk missing"));
      maps.load(() => resolve(maps));
    };
    if (kakaoMaps()) return ready();
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`;
    script.async = true;
    script.onload = ready;
    // 도메인 미등록(401) · 카카오맵 사용 설정 OFF(403) 도 여기로 온다 → 부모가 OSM 지도로 되돌린다
    script.onerror = () => reject(new Error("kakao sdk load failed"));
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    sdkPromise = null;
    throw error;
  });
  return sdkPromise;
}

interface KakaoRouteMapProps {
  apiKey: string;
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
  route?: WalkRoute;
  access?: AccessHint[];
  onError: () => void;
}

/**
 * 카카오 지도. Leaflet 지도와 **같은 것**을 그린다: 실제 보행 경로(구간별 색) · 가까운 지하철 출구 ·
 * 겹치면 부채꼴로 펼쳐지는 번호 핀(`map-shared.ts`). 키를 넣어 지도가 바뀌어도 코스는 똑같이 읽혀야 한다.
 */
export function KakaoRouteMap({ apiKey, stops, activeStop, onSelect, route, access, onError }: KakaoRouteMapProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KMap | null>(null);
  const [maps, setMaps] = useState<KakaoMaps | null>(null);
  const [zoomTick, setZoomTick] = useState(0); // 줌이 바뀌면 핀 펼침을 다시 계산한다
  const handlers = useRef({ onSelect, onError });
  const fitRef = useRef<() => void>(() => undefined);
  useEffect(() => {
    handlers.current = { onSelect, onError };
  }, [onSelect, onError]);

  useEffect(() => {
    let alive = true;
    loadKakao(apiKey)
      .then((m) => alive && setMaps(m))
      .catch(() => alive && handlers.current.onError());
    return () => {
      alive = false;
    };
  }, [apiKey]);

  // 지도는 한 번만 만든다
  useEffect(() => {
    const box = boxRef.current;
    const first = stops[0];
    if (!maps || !box || !first || mapRef.current) return;
    const map = new maps.Map(box, { center: new maps.LatLng(first.place.lat, first.place.lng), level: 3 });
    map.addControl(new maps.ZoomControl(), maps.ControlPosition.BOTTOMRIGHT);
    const onZoom = () => setZoomTick((n) => n + 1);
    const onClick = () => handlers.current.onSelect(null);
    maps.event.addListener(map, "zoom_changed", onZoom);
    maps.event.addListener(map, "click", onClick);
    mapRef.current = map;
    return () => {
      maps.event.removeListener(map, "zoom_changed", onZoom);
      maps.event.removeListener(map, "click", onClick);
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 초기 중심은 첫 렌더의 스톱으로 충분하다
  }, [maps]);

  // 화면 맞춤: 경로가 아니라 **스톱 기준**(길이 돌아가면 지도가 축소돼 번호가 안 보인다)
  useEffect(() => {
    const map = mapRef.current;
    if (!maps || !map || stops.length === 0) return;
    fitRef.current = () => {
      const bounds = new maps.LatLngBounds();
      stops.forEach((s) => bounds.extend(new maps.LatLng(s.place.lat, s.place.lng)));
      map.relayout();
      map.setBounds(bounds, 170, 80, 70, 80); // 위쪽은 핀 높이 + 이름표만큼 넉넉히
      if (map.getLevel() > MAX_FIT_LEVEL) map.setLevel(MAX_FIT_LEVEL);
      setZoomTick((n) => n + 1);
    };
    fitRef.current();
  }, [maps, stops]);

  // 경로 · 출구 · 핀
  useEffect(() => {
    const map = mapRef.current;
    if (!maps || !map || stops.length === 0) return;
    const overlays: KOverlay[] = [];
    const toLatLng = ([lat, lng]: LatLngTuple) => new maps.LatLng(lat, lng);

    const straight = stops.map((s) => [s.place.lat, s.place.lng] as LatLngTuple);
    const real = route?.source === "osrm" && route.coordinates.length > 1;
    const path = real ? route.coordinates : straight;
    overlays.push(new maps.Polyline({ path: path.map(toLatLng), strokeWeight: 11, strokeColor: "#FFFFFF", strokeOpacity: 0.96, strokeStyle: "solid" }));
    splitByStops(path, stops).forEach((segment, i) => {
      overlays.push(
        new maps.Polyline({
          path: segment.map(toLatLng),
          strokeWeight: 6,
          strokeColor: stopColor(i + 1, stops.length), // 도착 스톱의 색
          strokeOpacity: 1,
          strokeStyle: real ? "solid" : "shortdot", // 실제 경로를 못 받았으면 점선(직선 연결)임을 드러낸다
        }),
      );
    });

    // 0×0 기준점을 좌표에 놓고, 그 안의 핀·배지가 CSS 로 자리를 잡는다 (Leaflet divIcon 과 같은 방식 → 같은 CSS)
    const anchor = (html: string) => {
      const el = document.createElement("div");
      el.style.cssText = "position:relative;width:0;height:0";
      el.innerHTML = html;
      return el;
    };

    const seen = new Set<string>();
    for (const hint of access ?? []) {
      const s = hint.subway;
      if (!s || seen.has(`${s.lat},${s.lng}`)) continue;
      seen.add(`${s.lat},${s.lng}`);
      const el = anchor(`<span class="jj-exit">${escapeHtml(s.station)}${s.exit ? ` ${escapeHtml(s.exit)}번` : ""}</span>`);
      overlays.push(new maps.CustomOverlay({ position: new maps.LatLng(s.lat, s.lng), content: el, xAnchor: 0, yAnchor: 0, zIndex: 1 }));
    }

    const projection = map.getProjection();
    const spread = spreadOverlaps(stops.map((s) => projection.containerPointFromCoords(new maps.LatLng(s.place.lat, s.place.lng))));
    stops.forEach((stop, i) => {
      const active = stop.position === activeStop;
      const el = anchor(pinHtml(stop.position, stop.place.name, stopColor(i, stops.length), active, spread[i]!));
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", `${stop.position}. ${stop.place.name}`);
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        handlers.current.onSelect(stop.position);
      });
      overlays.push(
        new maps.CustomOverlay({
          position: new maps.LatLng(stop.place.lat, stop.place.lng),
          content: el,
          xAnchor: 0,
          yAnchor: 0,
          zIndex: active ? 1000 : 100 + (stops.length - i), // 순번이 앞설수록 위에
          clickable: true,
        }),
      );
    });

    overlays.forEach((o) => o.setMap(map));
    return () => overlays.forEach((o) => o.setMap(null));
  }, [maps, zoomTick, stops, activeStop, route, access]);

  // 타임라인에서 고른 스톱이 화면 밖이면 데려온다
  useEffect(() => {
    const map = mapRef.current;
    const stop = stops.find((s) => s.position === activeStop);
    if (!maps || !map || !stop) return;
    const point = new maps.LatLng(stop.place.lat, stop.place.lng);
    if (!map.getBounds().contain(point)) map.panTo(point);
  }, [maps, activeStop, stops]);

  return (
    <div className="relative size-full">
      <div
        ref={boxRef}
        className="jj-map size-full bg-[#EAF1FF]"
        role="application"
        aria-label={`코스 지도: ${stops.map((s) => `${s.position}. ${s.place.name}`).join(", ")}`}
      >
        {!maps ? <span className="skeleton-shimmer block size-full" aria-hidden /> : null}
      </div>
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
