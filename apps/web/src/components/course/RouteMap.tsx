"use client";

import { useState } from "react";
import type { AccessHint, WalkRoute } from "@/lib/api/hooks";
import type { Stop } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { KakaoRouteMap } from "./KakaoRouteMap";
import { LeafletRouteMap } from "./LeafletRouteMap";
import { SvgRouteMap } from "./SvgRouteMap";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

interface RouteMapProps {
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
  /** 실제 보행 경로·가까운 역 출구 (카카오 · Leaflet 지도가 똑같이 그린다) */
  route?: WalkRoute;
  access?: AccessHint[];
  className?: string;
}

/**
 * NEXT_PUBLIC_KAKAO_MAP_KEY 가 있으면 카카오맵, 없거나 SDK 가 거절되면(도메인 미등록 401 · 사용 설정 OFF 403)
 * OpenStreetMap(Leaflet, 키 불필요), 그마저 타일을 받지 못하면 SVG 약도.
 * 어느 쪽이든 같은 props 를 받으므로 화면 쪽은 구분하지 않는다.
 */
export function RouteMap({ stops, activeStop, onSelect, route, access, className }: RouteMapProps) {
  const [kakaoFailed, setKakaoFailed] = useState(false);
  const [osmFailed, setOsmFailed] = useState(false);
  const useKakao = Boolean(KAKAO_KEY) && !kakaoFailed;

  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      {useKakao && KAKAO_KEY ? (
        <KakaoRouteMap apiKey={KAKAO_KEY} stops={stops} activeStop={activeStop} onSelect={onSelect} route={route} access={access} onError={() => setKakaoFailed(true)} />
      ) : !osmFailed ? (
        <LeafletRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} route={route} access={access} onError={() => setOsmFailed(true)} />
      ) : (
        <SvgRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} />
      )}
    </div>
  );
}
