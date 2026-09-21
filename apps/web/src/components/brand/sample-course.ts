import type { ReceiptItem } from "./Receipt";

/**
 * "이 예산이면 이런 하루" — 업종 평균가로 만든 **예시** 코스. 실제 가게가 아니다(쓰는 곳에서 반드시 "예시"라고 적는다).
 * 히어로와 위저드 예산 단계가 같은 계산을 써서, 랜딩에서 본 영수증과 위저드에서 본 영수증이 어긋나지 않는다.
 */
const MEALS = [
  { name: "분식 · 김밥", price: 8000 },
  { name: "한식 · 백반", price: 11000 },
  { name: "양식 · 파스타", price: 15000 },
  { name: "고기 · 구이", price: 20000 },
  { name: "일식 · 오마카세풍", price: 32000 },
];
const CAFES = [
  { name: "테이크아웃 커피", price: 3000 },
  { name: "동네 카페", price: 6000 },
  { name: "디저트 카페", price: 9000 },
];
const PLAYS = [
  { name: "코인노래방", price: 3000 },
  { name: "보드게임 카페", price: 7000 },
  { name: "방탈출", price: 22000 },
];
const BARS = [
  { name: "맥주 한잔", price: 16000 },
  { name: "와인바", price: 25000 },
];

const best = <T extends { price: number }>(options: T[], cap: number): T | undefined =>
  [...options].reverse().find((o) => o.price <= cap);

/** 예산(1인)을 식사 → 카페 → 산책(무료) → 남는 만큼 술집 또는 놀거리 순으로 채운다. 합계는 절대 예산을 넘지 않는다. */
export function sampleCourse(perPerson: number, party: number): ReceiptItem[] {
  const items: ReceiptItem[] = [];
  let left = perPerson;
  const add = (label: string, pick?: { name: string; price: number }) => {
    if (!pick || pick.price > left) return;
    items.push({ label, name: pick.name, price: pick.price * party });
    left -= pick.price;
  };
  add("식사", best(MEALS, perPerson * 0.46) ?? MEALS[0]);
  add("카페", best(CAFES, perPerson * 0.18));
  items.push({ label: "산책", name: "공원 · 골목", price: 0 });
  const bar = best(BARS, left);
  if (bar) add("한잔", bar);
  add("놀거리", best(PLAYS, left));
  return items;
}
