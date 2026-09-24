/**
 * 첫 진입 인트로(/intro)와 서비스 홈("/")의 약속 (docs/40).
 * 클라이언트 전용 파일이 아니다 — 서버 컴포넌트(page.tsx)가 인라인 스크립트로 그대로 넣는다.
 */
export const ENTERED_KEY = "jj-entered";

/**
 * "/" 의 첫 페인트 전 게이트: 이번 방문(브라우저 세션)에 인트로를 아직 안 봤으면 인트로로.
 * 2026-09-24 창업자: "브라우저당 한 번"은 인트로가 다시는 안 보여서 적용이 안 된 것처럼 보였다 → **방문(세션)마다 한 번**.
 * 같은 방문 안에서 홈으로 돌아올 때는 다시 가지 않는다. 자동화 브라우저(검증 · E2E) · ?intro=0 · 저장소를 못 쓰면 그대로 홈.
 */
export const ENTRY_GATE = `(function(){try{if(sessionStorage.getItem("${ENTERED_KEY}")||navigator.webdriver||/[?&]intro=0/.test(location.search))return;location.replace("/intro")}catch(e){}})();`;

/**
 * "/intro" 의 첫 페인트 전 스크립트: 인트로를 본 것 자체를 입장으로 기록한다.
 * 버튼 클릭에서만 기록하면, 스크립트가 붙기 전(느린 폰 · 개발 서버)에 "입장하기"를 누른 사람은 기록이 남지 않아
 * 홈에 올 때마다 인트로로 되돌아갔다(2026-09-24 발견).
 */
export const MARK_ENTERED = `(function(){try{sessionStorage.setItem("${ENTERED_KEY}","1")}catch(e){}})();`;
