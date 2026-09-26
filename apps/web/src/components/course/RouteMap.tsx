"use client";

import { useState } from "react";
import type { AccessHint } from "@/lib/api/hooks";
import type { ErrandLeg, Stop } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { KakaoRouteMap } from "./KakaoRouteMap";
import { LeafletRouteMap } from "./LeafletRouteMap";
import type { MapRoute, NearbyPin } from "./map-shared";
import { SvgRouteMap } from "./SvgRouteMap";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

interface RouteMapProps {
  stops: Stop[];
  activeStop: number | null;
  onSelect: (position: number | null) => void;
  /** 실제 보행 경로·가까운 역 출구 (카카오 · Leaflet 지도가 똑같이 그린다) */
  route?: MapRoute;
  /** 카드를 눌렀을 때: 그 장소로 옮겨 가 확대한다 (n 이 바뀔 때마다 다시) */
  focus?: { position: number; n: number } | null;
  /** 바뀔 때마다 코스 전체가 보이게 다시 맞춘다 ("전체 코스 지도에서 보기") */
  fitKey?: number;
  access?: AccessHint[];
  /** 코스 밖의 주변 장소 하나를 번호 없는 핀으로 (SVG 약도는 그리지 않는다) */
  nearby?: NearbyPin | null;
  onNearby?: () => void;
  /** 꼭 들를 곳과 코스 사이의 구간 (docs/59 #7). SVG 약도는 그리지 않는다 */
  errand?: ErrandLeg | null;
  className?: string;
}

/**
 * NEXT_PUBLIC_KAKAO_MAP_KEY 가 있으면 카카오맵, 없거나 SDK 가 거절되면(도메인 미등록 401 · 사용 설정 OFF 403)
 * OpenStreetMap(Leaflet, 키 불필요), 그마저 타일을 받지 못하면 SVG 약도.
 * 어느 쪽이든 같은 props 를 받으므로 화면 쪽은 구분하지 않는다.
 */
export function RouteMap({ stops, activeStop, onSelect, route, access, focus, fitKey, nearby, onNearby, errand, className }: RouteMapProps) {
  const [kakaoFailed, setKakaoFailed] = useState(false);
  const [osmFailed, setOsmFailed] = useState(false);
  const useKakao = Boolean(KAKAO_KEY) && !kakaoFailed;

  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      {useKakao && KAKAO_KEY ? (
        <KakaoRouteMap apiKey={KAKAO_KEY} stops={stops} activeStop={activeStop} onSelect={onSelect} route={route} access={access} focus={focus} fitKey={fitKey} nearby={nearby} onNearby={onNearby} errand={errand} onError={() => setKakaoFailed(true)} />
      ) : !osmFailed ? (
        <LeafletRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} route={route} access={access} focus={focus} fitKey={fitKey} nearby={nearby} onNearby={onNearby} errand={errand} onError={() => setOsmFailed(true)} />
      ) : (
        <SvgRouteMap stops={stops} activeStop={activeStop} onSelect={onSelect} />
      )}
    </div>
  );
}
