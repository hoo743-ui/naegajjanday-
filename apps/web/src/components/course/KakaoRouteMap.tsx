"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2 } from "lucide-react";
import type { AccessHint } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { minutes, transportLabel } from "@/lib/format";
import { routeColor, stopColor } from "./colors";
import { escapeHtml, landingClock, layoutLeg, legChipHtml, legsOf, nearbyHtml, passed, pinHtml, spreadOverlaps, type LatLngTuple, type MapRoute, type NearbyPin, type Pt } from "./map-shared";

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
  getProjection(): { containerPointFromCoords(point: KLatLng): KPoint; coordsFromContainerPoint(point: KPoint): KLatLng };
  addControl(control: unknown, position: unknown): void;
}
interface KOverlay {
  setMap(map: KMap | null): void;
}
export interface KakaoMaps {
  load(callback: () => void): void;
  LatLng: new (lat: number, lng: number) => KLatLng;
  LatLngBounds: new () => KBounds;
  Point: new (x: number, y: number) => KPoint;
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

/**
 * 화면 맞춤의 여백(위 · 오른쪽 · 아래 · 왼쪽). 위쪽은 핀 높이 + 이름표만큼 넉넉히 두되, 지도 칸에 비례해 줄인다 —
 * 모바일 절반 지도(약 250px)에 고정 여백 170 + 70 을 주면 남는 칸이 10px 뿐이라 서울 전체까지 물러났다.
 */
function fitPadding(box: HTMLElement | null): [number, number, number, number] {
  const h = box?.clientHeight ?? 600;
  const w = box?.clientWidth ?? 600;
  const side = Math.round(Math.min(80, w * 0.12));
  return [Math.round(Math.min(170, h * 0.3)), side, Math.round(Math.min(70, h * 0.1)), side];
}

/** 지도와 로드뷰(RoadviewPeek)가 같은 SDK 를 한 번만 받는다 */
export function loadKakao(key: string): Promise<KakaoMaps> {
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
  route?: MapRoute;
  access?: AccessHint[];
  /** 카드를 눌렀을 때: 그 장소로 옮겨 가 확대한다 (n 이 바뀔 때마다 다시) */
  focus?: { position: number; n: number } | null;
  /** 바뀔 때마다 코스 전체가 보이게 다시 맞춘다 ("전체 코스 지도에서 보기") */
  fitKey?: number;
  /** 코스 밖의 주변 장소 하나: 번호 없는 핀으로 띄우고, 코스와 함께 보이게 맞춘다 */
  nearby?: NearbyPin | null;
  /** 주변 장소 핀을 눌렀을 때 (장소 상세 열기) */
  onNearby?: () => void;
  onError: () => void;
}

/**
 * 카카오 지도. Leaflet 지도와 **같은 것**을 그린다: 실제 보행 경로(구간별 색) · 가까운 지하철 출구 ·
 * 겹치면 부채꼴로 펼쳐지는 번호 핀(`map-shared.ts`). 키를 넣어 지도가 바뀌어도 코스는 똑같이 읽혀야 한다.
 */
export function KakaoRouteMap({ apiKey, stops, activeStop, onSelect, route, access, focus, fitKey, nearby, onNearby, onError }: KakaoRouteMapProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KMap | null>(null);
  const landingRef = useRef(landingClock());
  const [maps, setMaps] = useState<KakaoMaps | null>(null);
  const [zoomTick, setZoomTick] = useState(0); // 줌이 바뀌면 핀 펼침을 다시 계산한다
  const handlers = useRef({ onSelect, onError, onNearby });
  const fitRef = useRef<() => void>(() => undefined);
  // 화면 맞춤(바텀시트 크기 변화 등)이 띄워 둔 주변 장소를 화면 밖으로 밀어내지 않게, 맞춤에 함께 넣는다
  const nearbyRef = useRef(nearby);
  nearbyRef.current = nearby;
  useEffect(() => {
    handlers.current = { onSelect, onError, onNearby };
  }, [onSelect, onError, onNearby]);

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

  // 화면 맞춤: 스톱 + 실제 경로. 길이 크게 돌아가면 선이 화면 밖으로 나갔다 들어와 어디로 가는지 읽을 수 없다.
  // 그렇다고 한없이 축소하지는 않는다 — MAX_FIT_LEVEL 에서 멈춰 번호 핀이 읽히는 크기를 지킨다.
  useEffect(() => {
    const map = mapRef.current;
    if (!maps || !map || stops.length === 0) return;
    fitRef.current = () => {
      const pins = new maps.LatLngBounds();
      stops.forEach((s) => pins.extend(new maps.LatLng(s.place.lat, s.place.lng)));
      const bounds = new maps.LatLngBounds();
      stops.forEach((s) => bounds.extend(new maps.LatLng(s.place.lat, s.place.lng)));
      const extra = nearbyRef.current;
      if (extra) {
        pins.extend(new maps.LatLng(extra.lat, extra.lng));
        bounds.extend(new maps.LatLng(extra.lat, extra.lng));
      }
      if (route?.routed) route.coordinates.forEach(([lat, lng]) => bounds.extend(new maps.LatLng(lat, lng)));
      map.relayout();
      // 핀은 무엇보다 먼저다: 차로 야경을 보러 가는 코스 · 여러 동네를 잇는 코스는 동네 하나보다 넓다.
      // 확대 제한(MAX_FIT_LEVEL)은 "길이 돌아가서 넓어진 만큼"에만 건다 → 모든 번호 핀은 언제나 화면 안에 있다.
      const pad = fitPadding(boxRef.current);
      map.setBounds(pins, ...pad);
      const pinsLevel = map.getLevel();
      map.setBounds(bounds, ...pad);
      if (map.getLevel() > Math.max(MAX_FIT_LEVEL, pinsLevel)) {
        map.setBounds(pins, ...pad);
        if (pinsLevel < MAX_FIT_LEVEL) map.setLevel(MAX_FIT_LEVEL);
      }
      setZoomTick((n) => n + 1);
    };
    fitRef.current();
  }, [maps, stops, route]);

  // 경로 · 출구 · 핀
  useEffect(() => {
    const map = mapRef.current;
    if (!maps || !map || stops.length === 0) return;
    const overlays: KOverlay[] = [];

    // 구간마다: 진행 방향 오른쪽으로 비켜 그린 선 · 핀까지의 점선 · 방향/시간 표시 (규칙은 map-shared.ts)
    const projection = map.getProjection();
    const toPx = ([lat, lng]: LatLngTuple): Pt => projection.containerPointFromCoords(new maps.LatLng(lat, lng));
    const toCoords = (p: Pt) => projection.coordsFromContainerPoint(new maps.Point(p.x, p.y));
    const pinsPx = stops.map((s) => toPx([s.place.lat, s.place.lng]));
    const legs = legsOf(stops, route, (mode, min) => `${transportLabel(mode)} ${minutes(min)}`);
    const layouts = legs.map((leg, i) => layoutLeg(leg.coords.map(toPx), pinsPx[i]!, pinsPx[i + 1]!, pinsPx));
    const stroke = (path: Pt[], strokeWeight: number, strokeColor: string, strokeStyle: string, strokeOpacity = 1) =>
      overlays.push(new maps.Polyline({ path: path.map(toCoords), strokeWeight, strokeColor, strokeOpacity, strokeStyle }));
    // 흰 테두리를 먼저 모두 깔고 그 위에 색 선을 올린다 → 뒤 구간의 테두리가 앞 구간의 선을 덮지 않는다
    layouts.forEach((layout, i) => {
      if (!legs[i]!.routed) return;
      stroke(layout.line, 11, "#FFFFFF", "solid", 0.96);
      layout.connectors.forEach((pair) => stroke(pair, 8, "#FFFFFF", "solid", 0.9));
    });
    // 고른 장소로 들어오는 구간은 맨 나중에(맨 위에) 그린다
    const order = layouts.map((_, i) => i).sort((a, b) => Number(stops[a + 1]!.position === activeStop) - Number(stops[b + 1]!.position === activeStop));
    order.forEach((i) => {
      const layout = layouts[i]!;
      const color = routeColor(stops[i + 1]!.position, activeStop);
      stroke(layout.line, 6, color, legs[i]!.routed ? "solid" : "shortdot"); // 실제 경로가 아니면 점선(곧게 이음)임을 드러낸다
      if (legs[i]!.routed) layout.connectors.forEach((pair) => stroke(pair, 4, color, "shortdot"));
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

    layouts.forEach((layout, i) => {
      if (!layout.chip || !legs[i]!.label) return;
      const el = anchor(legChipHtml(legs[i]!.label, routeColor(stops[i + 1]!.position, activeStop), layout.chip.angle));
      overlays.push(new maps.CustomOverlay({ position: toCoords(layout.chip), content: el, xAnchor: 0, yAnchor: 0, zIndex: 50 }));
    });

    const spread = spreadOverlaps(pinsPx, boxRef.current ? { w: boxRef.current.clientWidth, h: boxRef.current.clientHeight } : undefined);
    const landing = landingRef.current(stops.map((s) => s.place.id).join(","));
    stops.forEach((stop, i) => {
      const active = stop.position === activeStop;
      const el = anchor(pinHtml(stop.position, stop.place.name, stopColor(i, stops.length), active, spread[i]!, landing, passed(stop)));
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

  // 바텀시트 단계가 바뀌면 지도 칸의 높이가 달라진다 → 다 바뀐 뒤 한 번만 코스 전체를 다시 맞춘다
  useEffect(() => {
    const box = boxRef.current;
    if (!box || typeof ResizeObserver === "undefined") return;
    let last = box.clientHeight;
    let timer = 0;
    const observer = new ResizeObserver(() => {
      const height = box.clientHeight;
      if (Math.abs(height - last) < 8) return;
      last = height;
      if (height < 40) return; // 접힌 지도(목록 전체)는 맞추지 않는다: 다시 펼칠 때 맞춘다
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fitRef.current(), 260);
    });
    observer.observe(box);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, []);

  // 카드를 누르면: 그 장소로 옮겨 가서 동네가 읽히는 만큼 확대한다
  useEffect(() => {
    const map = mapRef.current;
    const stop = focus ? stops.find((s) => s.position === focus.position) : undefined;
    if (!maps || !map || !stop) return;
    if (map.getLevel() > 3) map.setLevel(3);
    map.panTo(new maps.LatLng(stop.place.lat, stop.place.lng));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- n 이 바뀔 때만 (같은 카드를 다시 눌러도 다시 옮긴다)
  }, [maps, focus?.n]);

  // "전체 코스 지도에서 보기"
  useEffect(() => {
    if (fitKey) fitRef.current();
  }, [fitKey]);

  // 주변 장소: 번호 없는 핀 하나. 코스 핀과 그 장소가 한 화면에 들어오게 맞춘다 → 코스에서 얼마나 떨어졌는지가 보인다
  useEffect(() => {
    const map = mapRef.current;
    if (!maps || !map || !nearby) return;
    const el = document.createElement("div");
    el.style.cssText = "position:relative;width:0;height:0";
    el.innerHTML = nearbyHtml(nearby.name);
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `${nearby.name} 자세히 보기`);
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      handlers.current.onNearby?.();
    });
    const at = new maps.LatLng(nearby.lat, nearby.lng);
    const overlay = new maps.CustomOverlay({ position: at, content: el, xAnchor: 0, yAnchor: 0, zIndex: 2000, clickable: true });
    overlay.setMap(map);
    const bounds = new maps.LatLngBounds();
    stops.forEach((s) => bounds.extend(new maps.LatLng(s.place.lat, s.place.lng)));
    bounds.extend(at);
    map.relayout();
    map.setBounds(bounds, ...fitPadding(boxRef.current));
    setZoomTick((n) => n + 1);
    return () => overlay.setMap(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 다른 곳을 고르거나 같은 곳을 다시 누를 때만 (n)
  }, [maps, nearby?.n, nearby?.lat, nearby?.lng]);

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
      />
      {/* 지도 컨테이너는 카카오 SDK 가 DOM 을 직접 만진다 → 그 안에 React 자식을 두지 않는다 (RoadviewPeek 에서 실제로 터졌다) */}
      {!maps ? <span className="skeleton-shimmer pointer-events-none absolute inset-0" aria-hidden /> : null}
      <button
        type="button"
        onClick={() => fitRef.current()}
        className="absolute top-3 right-3 z-[500] inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-white px-3.5 text-body-sm font-semibold text-ink-2 shadow-soft hover:bg-soft hover:text-ink"
      >
        <Maximize2 aria-hidden className="size-3.5" />
        코스 전체 보기
      </button>
    </div>
  );
}
