/**
 * 첫 진입 인트로(/intro)와 서비스 홈("/")의 약속 (docs/40).
 * 클라이언트 전용 파일이 아니다 — 서버 컴포넌트(page.tsx)가 인라인 스크립트로 그대로 넣는다.
 */
export const ENTERED_KEY = "jj-entered";

/**
 * "/" 의 첫 페인트 전 게이트: 처음 온 사람은 인트로로. 인트로를 본 적이 있거나 · 자동화 브라우저(검증 · E2E) · ?intro=0 이면 그대로 홈.
 * 저장소를 못 쓰면 홈(막히지 않게).
 */
export const ENTRY_GATE = `(function(){try{if(localStorage.getItem("${ENTERED_KEY}")||navigator.webdriver||/[?&]intro=0/.test(location.search))return;location.replace("/intro")}catch(e){}})();`;

/**
 * "/intro" 의 첫 페인트 전 스크립트: 인트로를 본 것 자체를 입장으로 기록한다.
 * 버튼 클릭에서만 기록하면, 스크립트가 붙기 전(느린 폰 · 개발 서버)에 "입장하기"를 누른 사람은 기록이 남지 않아
 * 홈에 올 때마다 인트로로 되돌아갔다(2026-09-24 발견).
 */
export const MARK_ENTERED = `(function(){try{localStorage.setItem("${ENTERED_KEY}","1")}catch(e){}})();`;
