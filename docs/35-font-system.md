# 35. 최종 폰트 체계 — SUIT = 기능 · Hahmlet = 브랜드

> 2026-09-23 창업자 결정으로 docs/26 의 글꼴 부분(§4 Pretendard · Noto Serif KR · Jua)을 대체한다. 글자 계단 · 굵기 원칙(docs/26 §2~3)의 **구조**는 그대로 두고 수치만 창업자 값으로 바꿨다.
> 토큰의 정본은 `apps/web/src/app/globals.css` 의 `@theme`, 글꼴 로딩은 `apps/web/src/app/layout.tsx`.

## 1. 서체는 둘뿐
| 서체 | 성격 | 쓰는 곳 | 로딩 |
|---|---|---|---|
| **SUIT Variable** | 정보 · 기능 · 신뢰 | 메뉴 · 버튼 · 입력 · 칩 · 본문 · 장소 정보 · 가격 · 예산 · 영수증 숫자 · 제품 화면의 h1(위저드 질문 · 내 코스 · 약관) | `next/font/local`, `@sun-typeface/suit` 의 가변 woff2 셀프호스팅(OFL-1.1). 빌드가 외부 폰트 서버에 기대지 않는다 |
| **Hahmlet** | 감성 · 브랜드 · 기억 | 히어로 · 섹션 제목(`font-serif`) · 브랜드 한 줄 · 로고 · 영수증 머리(`font-round`) | `next/font/google`, 가변 굵기 하나, `preload: false` |

- 제거: Pretendard(패키지 uninstall), Noto Serif KR, Jua. 둥근 서체는 더 쓰지 않는다 — `font-round` 는 이름만 남기고 Hahmlet 700 을 가리킨다.
- **금액은 언제나 SUIT**: `money` 유틸리티가 `font-family: var(--font-sans)` 를 직접 건다. Hahmlet 제목 안에 금액이 들어가도 숫자는 SUIT 800 · tabular-nums.
- OG 이미지(`lib/og.tsx`, satori)도 SUIT 정적 OTF(ExtraBold · Medium)를 읽는다.
- 세리프는 전역으로 걸지 않는다(docs/26 §4 원칙 유지). 기능 UI 에 Hahmlet 을 쓰지 않는다.

## 2. 글자 계단 (최종 수치)
| 토큰 | 모바일 → 데스크톱 | 행간 | 자간 | 굵기 · 역할 |
|---|---|---|---|---|
| `text-display-xl` | 38 → 64 | 1.12 | -0.025em | 히어로 (Hahmlet 600, 강조 한 단어 700) |
| `text-display` | 28 → 40 | 1.2 | -0.02em | 섹션 제목 (Hahmlet 600) |
| `text-h1` | 26 → 32 | 1.25 | -0.01em | 페이지 제목 (SUIT 700) |
| `text-h2` | 20 → 24 | 1.34 | -0.01em | 큰 카드 · 단계 제목 |
| `text-h3` | 18 → 20 | 1.4 | 0 | 카드 제목 (600) |
| `text-body-lg` | 17 | 1.55 | 0 | 강조 본문 (600) |
| `text-body` | 16 | 1.65 | 0 | 본문 · 버튼 · 입력 (기본값, 400) |
| `text-body-sm` | 14 | 1.5 | 0 | 캡션 · 보조 문구 |
| `text-caption` | 12 | 1.3 | 0 | 칩 · 작은 표지 (600) |
| `text-price-lg` | 38 → 56 | 1 | -0.02em | 예산 · 남은 돈 (800) |
| `text-price` | 24 → 32 | 1.1 | -0.015em | 영수증 합계 |
| `text-price-sm` | 21 | 1.14 | -0.01em | 장소 가격 · 1인당 |

- SUIT 는 자간 0 이 기본이다(Pretendard 시절의 -0.01em 을 모두 걷었다). 자간을 좁히는 것은 Hahmlet 제목과 큰 금액뿐.
- 본문 기본값이 15 → 16px 로 올랐다.
- 새 크기 토큰을 만들면 `src/lib/utils.ts` 의 `extendTailwindMerge` 목록에도 넣는다(docs/26 의 함정 그대로).

## 3. 히어로의 굵기 — 명세 700 → 600
Hahmlet 700 의 한글은 획 끝이 뭉툭해져 캡처에서 고딕처럼 읽혔다. CDP 로 실제 적용 글꼴이 Hahmlet-Bold 임을 확인한 뒤 내린 판단이다.
→ `.font-serif.text-display-xl` 은 600, 강조 한 단어(`.hero-em`)만 700.

## 4. 히어로 문장의 리듬
```
예산만 말하면,
하루가
영수증으로 나온다.
```
조건 한 줄 → 쉼 → 결과. 강조는 금색이 아니라 **크기와 굵기**로 준다: `.hero-em` = 1.0625em(64 → 68px) · 행간 1.08 · 700.

## 5. 함께 들어간 것 — 넓은 화면의 탭 알약
- `TabBar` 가 넓은 화면에서도 가운데 알약으로 뜬다. 스크롤이 `TAB_DOCK_AT`(320px)을 넘으면 떠오르고, 그때 헤더의 메뉴는 숨는다(`SiteHeader` 의 `handedOff`). 모바일 하단 탭은 그대로다.

## 6. 확인
- 2026-09-23 `qa-pass.mjs --only=1440,390` 36화면: 넘침 · 잘림 · 깨진 사진 0. 44px 미만 터치 영역(결과 화면 탭 · 조건 바꾸기)은 폰트 변경 전부터 있던 것.
- 캡처를 눈으로 확인: 랜딩 · 결과 · 장소 상세 · 공유 · 내 코스(로그인) — 히어로 · 로고 · 영수증 머리는 Hahmlet, 나머지는 SUIT.
- `npm run typecheck` · `lint` · `verify`.
