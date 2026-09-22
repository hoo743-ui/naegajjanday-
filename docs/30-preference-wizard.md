# 30. 적게 묻고 풍부하게 이해하기 — 선호 해석 레이어 · 세 질문 위저드 (2026-09-22, 진행 중)

> 요청: 취향 단계의 태그 30여 개를 한 화면에 늘어놓지 말고 "오늘 어떤 하루? · 얼마나 이동? · 꼭 원하는 것?" 세 질문으로.
> 세부 태그는 지우지 않고 "더 자세히" 안에. 사용자 말 → 구조화된 선호 → 엔진.

## 0. 조사 (수정 전)
- 위저드 4단계: 지역 · 목적 · 인원/예산/시간 · **취향**(스타일 2택 · 비/술/야구 토글 · 동네 명물 · 태그 31개 좋아요/피할래요 · 이동수단)이 한 화면.
- 엔진 입력: `style`(efficient|fun) + `preferences.liked_tags/disliked_tags` 원문 그대로. 해석 레이어 없음.
- 태그는 API `/meta/tags` 4묶음(activity · feature · food · mood). 장소 태그는 `tag_rules.json` 으로 이름·업종에서 파생 → 화면에 없는 태그도 점수에 쓰인다(유지).

## 1. 끝난 것 (API, 커밋됨)
- `domain/recommendation/preference.py` — `interpret(pace, move_style, wishes, liked, disliked)`:
  - pace: relaxed(한 곳에 오래 · 덜 걷기) · packed(촘촘히) · foodie(식사 비중 ×1.25 · 맛집 태그) · special(재미 우선 스타일 · 목적지 가치 ↑ · 활동/문화로 구조 대안). 최대 2개, "여유+알차게" = 곳 수는 그대로, 한 곳 한 곳을 더 좋게.
  - move_style: local · balanced · explorer → docs/29 의 편한 구간 · 탐색 고리(거리 필터 아님).
  - wishes: night · walk · exhibition · value · romantic → 태그 친화도 · 구조 힌트 · 예산 자세.
  - 세 층 분리: HARD(날짜·인원·예산 상한·시간창·술 한잔 포함 — 여기서 건드리지 않음) · PREFERENCE(원함·세부 태그, soft) · STYLE(pace). 명시적 "피할래요"가 암시된 좋아요를 이긴다. 충돌은 오류가 아니라 soft weight.
- 요청 `pace` · `move_style` · `wishes`, 스냅샷에 저장(바꾸기·순서도 같은 해석), `POST /v1/courses/interpret` → 확인 화면용 요약 문장.
- 테스트: `tests/unit/test_preference.py`(11), `tests/integration/test_best_day_api.py`(6: 기본 3단계만 · 야경 · 상충 · 해석 요약 · 잘못된 값 422).

## 2. 남은 것 (웹 위저드 — 초안은 `docs/30-wizard-draft/`)
- `PreferenceSteps.tsx.draft`: DayStep(선택 카드 4, 1~2개) · MoveStep(3 카드 + 이동수단 작은 줄, 힌트 "한 구간 보통 15분 안팎") · WishStep(대표 5개 + "더 자세히" 안에 비/술/야구 · 동네 명물 · 태그 4묶음 접기) · ConfirmView("좋아요. 이렇게 이해했어요." 영수증 모양, API 요약, 실패 시 같은 규칙의 로컬 요약).
- `preference.ts.draft`: 라벨 · 로컬 요약. `edit_wizard_v3.py`: schema(STEPS 6개 + pace/move_style/wishes) · types · analytics(preference_step_view 등 8개) · ReceiptProgress(6칸) · PlanWizard(확인 화면, "조금 더 알려주기", "이대로 코스 짜 주세요") 패치. `--apply` 없이 돌리면 앵커만 확인한다.
- 적용 순서: 초안 2개를 `src/components/plan/`, `src/lib/` 로 되돌림 → `edit_wizard_v3.py --apply` → tsc(초안의 오류는 이 패치가 풀어 준다) → E2E 위저드 흐름 갱신(journey "취향" 단계 · release/dong/trip/site-cycle/button/local/visual-audit 의 "다음" 횟수 → "코스 짜 주세요"가 보일 때까지 다음) → verify · E2E → 390px 확인.
- 이어서 창업자 대기열: 브랜드 디자인 시스템(영수증 · 경로 · 돈 · 하루 네 언어), 타이포그래피(Jua · Noto Serif 의 "AI 랜딩" 느낌 제거, 폰트 최소화, 히어로를 "오늘의 예산 → 오늘의 하루 → 영수증" 구조로).
