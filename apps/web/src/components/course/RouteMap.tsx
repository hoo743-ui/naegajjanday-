"use client";

import { useEffect, useRef, useState } from "react";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { LeafletRouteMap } from "./LeafletRouteMap";
import { SvgRouteMap } from "./SvgRouteMap";
import { stopColor } from "./colors";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

interface RouteMapProps {
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
  /** 실제 보행 경로·가까운 역 출구 (Leaflet 지도에서만 그린다) */
  route?: WalkRoute;
  access?: AccessHint[];
  className?: string;
}

/**
 * NEXT_PUBLIC_KAKAO_MAP_KEY 가 있으면 카카오맵, 없으면 OpenStreetMap(Leaflet, 키 불필요),
 * 그마저 타일을 받지 못하면 SVG 약도.
 * 어느 쪽이든 같은 props 를 받으므로 화면 쪽은 구분하지 않는다.
 */
export function RouteMap({ stops, activeStop, onSelect, route, access, className }: RouteMapProps) {
  const [kakaoFailed, setKakaoFailed] = useState(false);
  const [osmFailed, setOsmFailed] = useState(false);
  const useKakao = Boolean(KAKAO_KEY) && !kakaoFailed;

  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      {useKakao ? (
        <KakaoRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} onError={() => setKakaoFailed(true)} />
      ) : !osmFailed ? (
        <LeafletRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} route={route} access={access} onError={() => setOsmFailed(true)} />
      ) : (
        <SvgRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} />
      )}
    </div>
  );
}

// ── Kakao Maps JS SDK (필요한 만큼만 타입 선언) ─────────────────
interface KakaoLatLng {
  getLat(): number;
}
interface KakaoBounds {
  extend(point: KakaoLatLng): void;
}
interface KakaoMap {
  setBounds(bounds: KakaoBounds, top?: number, right?: number, bottom?: number, left?: number): void;
  relayout(): void;
}
interface KakaoOverlay {
  setMap(map: KakaoMap | null): void;
}
interface KakaoMaps {
  load(callback: () => void): void;
  LatLng: new (lat: number, lng: number) => KakaoLatLng;
  LatLngBounds: new () => KakaoBounds;
  Map: new (container: HTMLElement, options: { center: KakaoLatLng; level: number }) => KakaoMap;
  CustomOverlay: new (options: { position: KakaoLatLng; content: HTMLElement; yAnchor?: number; zIndex?: number }) => KakaoOverlay;
  Polyline: new (options: { path: KakaoLatLng[]; strokeWeight: number; strokeColor: string; strokeOpacity: number; strokeStyle: string }) => KakaoOverlay;
}
declare global {
  interface Window {
    kakao?: { maps: KakaoMaps };
  }
}

let sdkPromise: Promise<KakaoMaps> | null = null;

function loadKakao(key: string): Promise<KakaoMaps> {
  sdkPromise ??= new Promise<KakaoMaps>((resolve, reject) => {
    const ready = () => {
      const maps = window.kakao?.maps;
      if (!maps) return reject(new Error("kakao sdk missing"));
      maps.load(() => resolve(maps));
    };
    if (window.kakao?.maps) return ready();
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`;
    script.async = true;
    script.onload = ready;
    script.onerror = () => reject(new Error("kakao sdk load failed"));
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    sdkPromise = null;
    throw error;
  });
  return sdkPromise;
}

function KakaoRouteMap({ stops, activeStop, onSelect, onError }: Omit<RouteMapProps, "className"> & { onError: () => void }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMap | null>(null);
  const [maps, setMaps] = useState<KakaoMaps | null>(null);
  const handlers = useRef({ onSelect, onError });
  useEffect(() => {
    handlers.current = { onSelect, onError };
  }, [onSelect, onError]);

  useEffect(() => {
    if (!KAKAO_KEY) return;
    let alive = true;
    loadKakao(KAKAO_KEY)
      .then((m) => alive && setMaps(m))
      .catch(() => alive && handlers.current.onError());
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const box = boxRef.current;
    const first = stops[0];
    if (!maps || !box || !first) return;
    const map = (mapRef.current ??= new maps.Map(box, { center: new maps.LatLng(first.place.lat, first.place.lng), level: 4 }));
    const path = stops.map((s) => new maps.LatLng(s.place.lat, s.place.lng));
    const bounds = new maps.LatLngBounds();
    path.forEach((p) => bounds.extend(p));

    const overlays: KakaoOverlay[] = [
      new maps.Polyline({ path, strokeWeight: 9, strokeColor: "#FFFFFF", strokeOpacity: 0.95, strokeStyle: "solid" }),
      new maps.Polyline({ path, strokeWeight: 5, strokeColor: "#2F6BEA", strokeOpacity: 0.95, strokeStyle: "solid" }),
    ];
    stops.forEach((stop, i) => {
      const el = document.createElement("button");
      el.type = "button";
      el.textContent = String(stop.position);
      el.setAttribute("aria-label", `${stop.position}번 ${stop.place.name}`);
      el.dataset.position = String(stop.position);
      el.style.cssText = `width:34px;height:34px;border-radius:50%;border:3px solid #fff;background:${stopColor(i, stops.length)};color:#fff;font-weight:800;font-size:14px;box-shadow:0 6px 16px rgba(47,80,160,.35);cursor:pointer;transition:transform .2s`;
      el.addEventListener("mouseenter", () => handlers.current.onSelect(stop.position));
      el.addEventListener("mouseleave", () => handlers.current.onSelect(null));
      el.addEventListener("click", () => handlers.current.onSelect(stop.position));
      const pos = path[i];
      if (pos) overlays.push(new maps.CustomOverlay({ position: pos, content: el, yAnchor: 0.5, zIndex: 3 }));
    });
    overlays.forEach((o) => o.setMap(map));
    map.relayout();
    map.setBounds(bounds, 80, 60, 60, 60);
    return () => overlays.forEach((o) => o.setMap(null));
  }, [maps, stops]);

  // 타임라인에서 hover 한 스톱을 지도에서도 강조
  useEffect(() => {
    boxRef.current?.querySelectorAll<HTMLElement>("button[data-position]").forEach((el) => {
      el.style.transform = Number(el.dataset.position) === activeStop ? "scale(1.25)" : "scale(1)";
    });
  }, [activeStop, maps, stops]);

  return (
    <div ref={boxRef} className="size-full bg-[#EAF1FF]" role="application" aria-label="코스 지도">
      {!maps ? <span className="skeleton-shimmer block size-full" aria-hidden /> : null}
    </div>
  );
}
