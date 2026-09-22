/**
 * 지도와 타임라인의 색 (docs/25): 순번은 잉크, 고른 것만 파랑, 경로는 파랑 한 가지.
 * 예전에는 순번마다 파랑 → 보라 → 분홍으로 달랐다 — 종이 톤의 화면에서 지도만 따로 놀았다.
 */
export const PIN_INK = "#10192E";
export const ROUTE_BLUE = "#2A5BD7";

/** i번째 스톱의 번호 색. 모든 순번이 같은 잉크다(인자는 호출부를 그대로 두려고 남겼다) */
export function stopColor(_index?: number, _count?: number): string {
  return PIN_INK;
}

/** 구간(경로선 · 이동 시간 칩)의 색 */
export function routeColor(): string {
  return ROUTE_BLUE;
}
