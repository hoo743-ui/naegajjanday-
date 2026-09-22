/**
 * 지도와 타임라인의 색 (docs/25): 순번은 잉크, 고른 것만 파랑, 경로는 파랑 한 가지.
 * 예전에는 순번마다 파랑 → 보라 → 분홍으로 달랐다 — 종이 톤의 화면에서 지도만 따로 놀았다.
 */
export const PIN_INK = "#10192E";
export const ROUTE_BLUE = "#2A5BD7";
/** 다른 장소를 보고 있을 때의 나머지 구간: 흐린 회청색 (docs/27 §7) */
export const ROUTE_MUTED = "#A9B4CB";

/** i번째 스톱의 번호 색. 모든 순번이 같은 잉크다(인자는 호출부를 그대로 두려고 남겼다) */
export function stopColor(_index?: number, _count?: number): string {
  return PIN_INK;
}

/**
 * 구간(경로선 · 이동 시간 칩)의 색. 아무것도 고르지 않았으면 모두 파랑, 장소를 골랐으면 그 장소로 들어오는 구간만 파랑이고
 * 나머지는 흐린 회청색이다 — "지금 보는 곳까지 어떻게 가는지"가 먼저 읽힌다. 금색은 돈에만 쓰므로 경로에 쓰지 않는다.
 */
export function routeColor(arrivesAt?: number, activeStop?: number | null): string {
  if (activeStop == null || arrivesAt === undefined) return ROUTE_BLUE;
  return arrivesAt === activeStop ? ROUTE_BLUE : ROUTE_MUTED;
}
