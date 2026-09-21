"use client";

import { useEffect, useRef, useState } from "react";
import { loadKakao } from "./KakaoRouteMap";

interface RoadviewPeekProps {
  apiKey: string;
  lat: number;
  lng: number;
  name: string;
}

// 카카오 로드뷰 (쓰는 만큼만 타입 선언). 지도 SDK 와 같은 스크립트에 들어 있다.
interface KRoadviewClient {
  getNearestPanoId(position: unknown, radius: number, callback: (panoId: number | null) => void): void;
}
interface KRoadview {
  setPanoId(panoId: number, position: unknown): void;
}
interface KakaoRoadviewApi {
  LatLng: new (lat: number, lng: number) => unknown;
  Roadview: new (container: HTMLElement) => KRoadview;
  RoadviewClient: new () => KRoadviewClient;
}

/** 가게 앞에서 찍힌 거리뷰만 "그 지점의 모습"이다 — 이보다 멀면 다른 골목을 보여 주게 된다 */
const NEAREST_PANO_M = 60;
const TILE_CHECK_MS = 4000;
const MIN_TILES = 2;

/**
 * 그 지점의 실제 모습: 카카오 로드뷰를 그 자리에서 바로 연다.
 * 우리가 사진을 모으거나 저장하지 않는다 — 공식 SDK 가 카카오 서버에서 그때그때 그린다(크롤링 금지 원칙).
 * 가까운 거리뷰가 없으면 없다고 말한다. 비슷한 곳의 사진으로 때우지 않는다.
 */
export function RoadviewPeek({ apiKey, lat, lng, name }: RoadviewPeekProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "none" | "error">("loading");

  useEffect(() => {
    let alive = true;
    let timer = 0;
    loadKakao(apiKey)
      .then((maps) => {
        const api = maps as unknown as KakaoRoadviewApi;
        const box = boxRef.current;
        if (!alive || !box) return;
        const position = new api.LatLng(lat, lng);
        new api.RoadviewClient().getNearestPanoId(position, NEAREST_PANO_M, (panoId) => {
          if (!alive) return;
          if (panoId === null) return setState("none");
          new api.Roadview(box).setPanoId(panoId, position);
          setState("ready");
          // 파노라마 번호는 있는데 타일을 못 받아 오는 지점이 있다(SDK 는 콘솔에만 알린다) → 회색 상자를 두지 말고 없다고 말한다
          timer = window.setTimeout(() => {
            const drawn = [...box.querySelectorAll("img")].filter((img) => img.complete && img.naturalWidth > 0).length;
            if (alive && drawn < MIN_TILES) setState("none");
          }, TILE_CHECK_MS);
        });
      })
      .catch(() => alive && setState("error"));
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [apiKey, lat, lng]);

  return (
    <div className="mt-3 overflow-hidden rounded-2xl border border-line">
      {/* 거리뷰 컨테이너는 카카오 SDK 가 DOM 을 직접 갈아 끼운다 → 그 안에 React 자식을 두면 안 된다
          (React 가 자기 자식을 지우려다 removeChild 에서 터져 페이지 전체가 에러 화면이 된다). 스켈레톤은 형제로 얹는다. */}
      <div className="relative h-[220px] w-full bg-soft" hidden={state === "none" || state === "error"}>
        <div ref={boxRef} role="img" aria-label={`${name} 앞 거리뷰`} className="size-full" />
        {state === "loading" ? <span className="skeleton-shimmer pointer-events-none absolute inset-0" aria-hidden /> : null}
      </div>
      {state === "none" ? <p className="p-4 text-[13px] text-muted-foreground">이 가게 앞에는 거리뷰가 없어요. 지도 앱에서 주변을 확인해 주세요.</p> : null}
      {state === "error" ? <p className="p-4 text-[13px] text-muted-foreground">거리뷰를 불러오지 못했어요.</p> : null}
      {state === "ready" ? <p className="px-3 py-1.5 text-[11.5px] text-muted-foreground">거리뷰 ⓒ Kakao · 촬영 시점의 모습이라 지금과 다를 수 있어요</p> : null}
    </div>
  );
}
