/**
 * "하루의 선" — 내가짠데이의 브랜드 선 (docs/25 §4). 한 획이 네 가지가 된다:
 *   한옥의 지붕선(과거) → 도시의 스카이라인(현재) → 지도의 경로(동선) → 영수증의 절취선(오늘의 하루).
 * 첫 진입 시퀀스가 이 선을 그리고, 랜딩 히어로는 같은 선을 옅게 깔아 둔다 — 인트로가 끝나도 선은 남아 있다.
 * 좌표계는 viewBox 0 0 1200 240, 바닥선 y=190.
 */
export const DAY_LINE_VIEWBOX = "0 0 1200 240";

/** 지붕선 → 스카이라인 → 경로. 절취선(점선)은 따로 그린다(그리기 애니메이션이 stroke-dasharray 를 쓰기 때문) */
export const DAY_LINE_PATH = [
  // 땅
  "M 30 190 H 110",
  // 한옥: 벽 → 처마 끝이 살짝 들린 지붕 → 용마루 → 반대쪽 처마 → 벽
  "V 160 Q 95 160 80 148 Q 130 140 150 118 H 250 Q 270 140 320 148 Q 305 160 290 160 V 190",
  // 땅
  "H 360",
  // 도시: 낮은 건물 · 높은 건물 · 탑 하나
  "V 120 H 392 V 150 H 420 V 88 H 452 V 132 H 480 V 104 H 506 V 150 H 530 L 543 58 L 556 150 H 590 V 124 H 616 V 190",
  // 경로: 두 곳을 들르며 흐르는 동선
  "H 640 C 690 190 700 140 745 140 S 800 196 840 172 S 872 150 890 150",
].join(" ");

/** 경로 위에 들르는 곳 (지도의 핀 자리) */
export const DAY_LINE_STOPS: [number, number][] = [
  [745, 140],
  [840, 172],
];

/** 절취선: 경로가 끝난 자리에서 영수증의 머리로 이어지는 구멍들 */
export const DAY_LINE_TEAR = { y: 150, from: 904, to: 1170, gap: 14 };

export const tearHoles = (): number[] => {
  const holes: number[] = [];
  for (let x = DAY_LINE_TEAR.from; x <= DAY_LINE_TEAR.to; x += DAY_LINE_TEAR.gap) holes.push(x);
  return holes;
};
