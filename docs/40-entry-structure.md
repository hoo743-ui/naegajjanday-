# 40. 진입 구조 — 인트로 · 홈 · 소개의 역할 분리

> 2026-09-24 창업자 요청. "홈을 설명 페이지로 쓰지 않는다. 인트로는 브랜드 각인, 홈은 사용 시작, 소개는 기획 의도, 코스 짜기 · 둘러보기는 실제 행동."

| 주소 | 역할 | 컴포넌트 |
|---|---|---|
| `/intro` | 첫 진입 브랜드 인트로. 내가 → 짠 → 데이 (약 3.5초) 뒤 "입장하기" · "내 하루 바로 짜기". 자동으로 넘어가지 않는다 | `components/landing/BrandIntro.tsx` (+ `globals.css .brand-intro` · `.bi-*`) |
| `/` | 서비스 홈 = 대시보드. 두 갈래 → 빠른 코스 만들기 → 오늘의 둘러보기 (docs/41) | `components/home/HomeDashboard.tsx` · `QuickCourse.tsx` |
| `/about` | 소개. 이름의 뜻(+ 인트로 다시 보기) → 예전 랜딩의 설명 섹션들(KoreaDay · HowItWorks · Differentiators · PurposeCards · FinalCta) | `app/(marketing)/about/page.tsx` · `components/landing/AboutName.tsx` |

## 첫 방문 판단
- `/` 의 첫 페인트 전 인라인 스크립트(`ENTRY_GATE`)가 `localStorage.jj-entered` 를 본다. 없으면 `location.replace("/intro")`.
- 표식은 인트로의 "입장하기" · "내 하루 바로 짜기" · "건너뛰기"가 남긴다 → 재방문은 바로 홈.
- 건너뜀: 자동화 브라우저(`navigator.webdriver` — verify · E2E · 캡처), `?intro=0`. 저장소를 못 쓰면 홈(막히지 않게).
- 인트로를 다시 보는 길: 소개(/about)의 "인트로 다시 보기", 또는 `/intro` 직접.

## 인트로의 접근성
- 모션 최소화: 움직임 없이 마지막 화면(워드마크 · 세 낱말의 뜻 · 버튼)이 바로 보인다.
- 버튼이 나타날 즈음(3.6s) 키보드 초점이 "입장하기"로 간다. 건너뛰기는 처음부터 오른쪽 위.

## 내비게이션
- 헤더: 코스 짜기 · 둘러보기 · 소개 · 내 코스 · (로그인 | 닉네임 · 로그아웃).
- 모바일 아래 탭은 행동 넷(홈 · 둘러보기 · 코스 짜기 · 내 코스) 그대로 — 소개는 탭이 아니라 헤더 오른쪽의 작은 링크. 읽는 곳은 자주 가는 곳이 아니다.
- 로그아웃 버튼은 헤더에(로그인했을 때만).
