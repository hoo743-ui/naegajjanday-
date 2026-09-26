import type { PlaceSummary } from "@/lib/api/types";

/**
 * 한 장소를 밖(지도 앱)에서 여는 주소 (docs/44 · docs/61 "각 칸이 네이버 · 카카오 장소 페이지로"). 예약 · 결제는 우리가 하지 않는다 —
 * 그 장소의 페이지(예약 · 메뉴 · 후기가 거기 있다)로 보낸다. 같은 상호가 전국에 많아 주소의 시 · 구를 붙여 찾는다.
 */
export function placeQuery(place: Pick<PlaceSummary, "name" | "address">): string {
  return [place.address?.split(" ").slice(1, 3).join(" "), place.name].filter(Boolean).join(" ");
}

export const kakaoSearchUrl = (place: Pick<PlaceSummary, "name" | "address">) => `https://map.kakao.com/link/search/${encodeURIComponent(placeQuery(place))}`;
export const naverSearchUrl = (place: Pick<PlaceSummary, "name" | "address">) => `https://map.naver.com/p/search/${encodeURIComponent(placeQuery(place))}`;

/**
 * 대개 예약 · 예매부터 하는 곳 (docs/61 §실사용 4: "공방은 대개 예약제인데 바로 들어가는 것으로 짰다").
 * 예약 여부 자료는 없다 → "필요할 수 있어요"로만 말한다.
 */
const BOOKING_CATEGORIES = new Set(["activity.craft", "activity.escape", "activity.cinema", "culture.cinema", "activity.stadium"]);
export const mayNeedBooking = (category: string) => BOOKING_CATEGORIES.has(category);
