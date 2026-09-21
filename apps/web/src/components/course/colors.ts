/** 경로 그라디언트(파랑 → 보라 → 핑크) 위에서 i번째 스톱의 색. 지도 핀과 타임라인 번호가 같은 색을 쓴다. */
const STOPS: [number, number, number][] = [
  [47, 107, 234], // #2F6BEA
  [142, 139, 255], // #8E8BFF
  [255, 111, 165], // #FF6FA5
];

export function stopColor(index: number, count: number): string {
  const t = count <= 1 ? 0 : Math.min(1, Math.max(0, index / (count - 1)));
  const scaled = t * (STOPS.length - 1);
  const lo = Math.floor(scaled);
  const hi = Math.min(STOPS.length - 1, lo + 1);
  const f = scaled - lo;
  const a = STOPS[lo] ?? STOPS[0]!;
  const b = STOPS[hi] ?? a;
  const mix = (k: 0 | 1 | 2) => Math.round(a[k] + (b[k] - a[k]) * f);
  return `rgb(${mix(0)} ${mix(1)} ${mix(2)})`;
}
