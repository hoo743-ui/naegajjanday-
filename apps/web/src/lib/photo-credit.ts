/**
 * 그 장소의 실제 사진에 붙이는 출처 표기.
 * 한국관광공사 TourAPI 사진은 공공누리(출처표시) 조건이라, 보여 주는 곳마다 출처를 밝혀야 한다.
 * 업종 대표 "예시 사진"(Wikimedia)의 표기는 각 컴포넌트가 따로 한다 — 그건 그 장소의 사진이 아니기 때문.
 */
export function photoCredit(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.includes("visitkorea.or.kr")) return "사진 ⓒ한국관광공사";
  return null;
}

/**
 * Next 이미지 최적화(`/_next/image`)를 거칠 수 있는 사진인가 — 지금은 아무것도 아니다.
 * 한국관광공사 원본(940px·90~640KB)을 줄여 받으려고 켰더니, 우리 서버가 수십 장을 동시에 요청하는 순간
 * 관광공사 서버가 느려져 Next 의 업스트림 제한 시간에 걸리고 사진이 500 으로 깨졌다(E2E 가 잡음).
 * 브라우저가 직접 받으면 깨지지는 않는다. 제대로 된 해법은 출시 전에 사진을 우리 저장소/CDN 으로 옮겨
 * 크기별로 만들어 두는 것 — 그때 이 함수가 그 호스트를 true 로 돌려주면 된다.
 */
export function canOptimize(_url: string | null | undefined): boolean {
  return false;
}
