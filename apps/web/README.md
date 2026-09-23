# 내가짠데이 — web

예산 기반 코스 추천 서비스의 프론트엔드. Next.js 15 (App Router · React 19 · TypeScript strict) + Tailwind CSS v4 + shadcn/ui.

디자인 정본은 저장소 루트의 `index.html` 이다. 색·그라디언트·그림자·24px 라운드·폰트(Gothic A1 + Jua)·짠이 SVG 를 그대로 옮겼다 (`src/app/globals.css`, `src/components/mascot/Jjani.tsx`).

## 빠른 시작

```bash
cd apps/web
npm install
cp .env.example .env.local

# 1) 백엔드(apps/api)가 http://localhost:8000 에 떠 있을 때
npm run dev

# 2) 백엔드 없이 화면만 개발할 때 — MSW 목 API
NEXT_PUBLIC_API_MOCKING=enabled npm run dev        # PowerShell: $env:NEXT_PUBLIC_API_MOCKING='enabled'; npm run dev
```

| 명령 | 설명 |
|---|---|
| `npm run dev` / `build` / `start` | Next.js |
| `npm run lint` | ESLint (경고 0개 강제) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run gen:api` | 백엔드 OpenAPI(`/v1/openapi.json`) → `src/lib/api/schema.gen.ts` (openapi-typescript) |
| `npm run msw:init` | `public/mockServiceWorker.js` 재생성 (msw 버전을 올렸을 때) |

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/v1` | API 베이스 URL |
| `NEXT_PUBLIC_SITE_URL` | `http://localhost:3000` | OG 메타의 절대 주소 |
| `NEXT_PUBLIC_API_MOCKING` | (없음) | **`enabled` 일 때만** MSW 목 API. 아래 참고 |
| `NEXT_PUBLIC_KAKAO_MAP_KEY` | (없음) | 있으면 카카오맵 JS SDK, 없으면 SVG 약도 |
| `NEXT_PUBLIC_GA4_ID` / `NEXT_PUBLIC_POSTHOG_KEY`(+`_HOST`) / `NEXT_PUBLIC_MIXPANEL_TOKEN` | (없음) | 키가 있는 분석 어댑터만 동적 로드 |

## 목(MOCK) API — 개발 전용

`NEXT_PUBLIC_API_MOCKING=enabled` 일 때만 켜진다. 켜져 있으면 **화면 왼쪽 아래에 `MOCK` 배지**가 항상 떠 있다.

- 브라우저: `src/lib/api/mock-ready.ts` 가 서비스 워커를 띄우고, 모든 fetch 가 그 준비를 기다린다. 꺼져 있으면 `src/mocks/` 청크는 로드되지 않는다.
- 서버(generateMetadata 등): `src/instrumentation.ts` 가 `msw/node` 를 켠다.
- 핸들러와 픽스처(`src/mocks/`)는 `docs/03-api-spec.md` 의 스키마를 따른다. 코스 생성은 실제 알고리즘(docs/06)의 모양만 흉내 낸 장난감 엔진이다.
- 목 모드에서는 `/my` · `/admin` 미들웨어 가드가 꺼지고, 개발용 **관리자 계정으로 자동 로그인**된다. `/course/demo` 로 결과 화면을 바로 볼 수 있다.
- 운영 Docker 이미지는 이 변수를 받지 않고 `mockServiceWorker.js` 도 지운다.

**화면 컴포넌트는 `src/mocks/` 를 import 하지 않는다.** 지역·목적·태그·장소 목록은 전부 API 에서 온다. API 가 죽어 있으면 가짜 데이터로 대체하지 않고 짠이 에러 상태 + "다시 시도" 를 보여 준다. 유일한 예외는 랜딩 히어로의 3막 애니메이션(`components/landing/HeroSequence.tsx`)으로, `index.html` 의 폰 목업과 같은 "연출된 일러스트"다.

## 구조

```
src/
  app/
    layout.tsx · providers.tsx · globals.css   # 토큰(CSS 변수) + Tailwind v4 @theme
    (marketing)/page.tsx                        # 랜딩
    plan/ · course/[id]/ · explore/ · chat/ · my/ · login/
    admin/{page,places,attractions,events,banners,regions,scoring,users,recommendations}
    loading.tsx · not-found.tsx · error.tsx · global-error.tsx   # 전부 짠이
  components/
    mascot/   Jjani(표정 6종, 파츠별 Motion) · JjaniBubble · JjaniLoader · EmptyState/ErrorState
    landing/  Hero · HeroSequence(GSAP ScrollTrigger) · HowItWorks · Differentiators · PurposeCards · FinalCta
    plan/     PlanWizard · steps · schema(zod)
    course/   CourseView · CourseTimeline · StopCard · ScoreBreakdown · BudgetBar · RouteMap(+SvgRouteMap) · AlternativeTabs · SwapMenu · NearbyEvents
    explore/ · chat/ · my/ · login/ · admin/ · layout/ · ui/(shadcn)
  lib/
    api/        client(fetch + problem+json → ApiError.code) · types · hooks · admin · sse · mock-ready
    analytics/  track()/page() + ga4 · posthog · mixpanel 어댑터 · events(타입 카탈로그)
    auth/       token(메모리 access + HttpOnly refresh) · AuthProvider · middleware
    format.ts · mascot-copy.ts(에러 code → 표정·문구)
  mocks/        MSW 핸들러 · 픽스처 (개발 전용)
  middleware.ts # /my, /admin 가드 (로직은 lib/auth/middleware.ts)
```

## 설계 메모

- **에러 → 짠이**: API 는 RFC 9457 problem+json 을 준다. `client.ts` 가 `ApiError(code)` 로 바꾸고 `mascot-copy.ts` 가 code 별 표정·문구·다음 행동을 고른다 (`BUDGET_TOO_LOW` → sorry + "예산 다시 정하기").
- **인증**: access token 은 메모리에만, refresh 는 API 가 심는 HttpOnly 쿠키 `rt`. 401 이면 refresh 를 한 번(동시 요청은 하나로 합쳐서) 시도하고 재요청한다. 미들웨어는 쿠키 유무만 보는 낙관적 가드고, 실제 권한은 API 가 판단한다.
- **모션**: Motion(`motion/react`) + CSS. `prefers-reduced-motion` 이면 Motion 은 `MotionConfig reducedMotion="user"`, CSS 애니메이션은 전역 미디어쿼리로 끈다. 브랜드 인트로(/intro)는 CSS 시간표로 돈다(docs/38 · 40).
- **결과 화면의 점수 설명**: `ScoreBreakdown` 은 8개 피처의 적합도(f)를 막대로 보여 준다. 종합 점수는 목적별 가중치(w)를 곱한 합이라 막대 평균과 다르다는 점을 화면에 밝힌다.
- **API 타입**: `lib/api/types.ts` 는 docs/03 을 손으로 옮긴 것. 백엔드가 뜨면 `npm run gen:api` 로 생성한 타입으로 교체한다. 문서에 응답 예시가 없는 엔드포인트(코스 상세의 `request`/`siblings`/`og`, 관리자 분석 등)는 이 파일의 모양이 프론트의 제안이다.

## Docker

```bash
docker build -t njd-web --build-arg NEXT_PUBLIC_API_URL=https://api.naegajjanday.com/v1 apps/web
docker run --rm -p 3000:3000 njd-web
```

`output: "standalone"` · 3-stage · UID 1001 `nextjs` 사용자로 실행.
