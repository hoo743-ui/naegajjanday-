# 18. 추천 품질 평가 — 아이디어를 1분 안에 시험하는 법

> 추천이 "어설픈지"를 사이트를 눌러 보며 판단하면 느리고, 같은 조건으로 다시 볼 수 없다.
> `eval-courses` 는 **실제 서비스와 똑같은 파이프라인**을 시나리오 행렬로 돌려 점수표를 낸다.
> HTTP 도, DB 기록도, 생성 한도도 없다. 120개 시나리오에 약 50초.

## 1. 한 줄 사용법 (`apps/api` 에서)

```bash
uv run python -m app.cli eval-courses                       # 4개 지역 × 5개 목적 × 3개 시각 × 2개 스타일 = 120
uv run python -m app.cli eval-courses --scope full          # 20개 지역 = 600 (약 5분)
uv run python -m app.cli eval-courses --save before         # 지금 상태를 기준선으로 저장
uv run python -m app.cli eval-courses --compare before      # 기준선 대비 무엇이 좋아지고 나빠졌나
uv run python -m app.cli eval-courses --region seoul-hongdae --purpose date --show   # 코스를 한 줄씩 직접 읽기
```

## 2. 아이디어 → 적용 → 판정 루프

1. `--save before` 로 기준선을 찍는다.
2. **데이터 파일 하나**를 고친다 (코드 수정·서버 재시작 불필요 — 하네스는 매번 새로 읽는다).

| 바꾸고 싶은 것 | 파일 |
|---|---|
| 목적별 가중치·태그 친화도·템플릿·슬롯 비중 | `data/seed/purposes.json` → `seed-config` |
| 코스 스타일(재미 우선 등)의 효과 | `app/domain/recommendation/style.py` 의 기본값, 또는 목적별 `params.styles` |
| 업종별 기본 영업시간 | `data/hours/default_hours.json` |
| 태그 도출·체인점·법인 상호·간판 이름 | `data/tagging/tag_rules.json` |
| 가격 추정 | `data/bulk/price_prior.json` |
| **무엇을 결함으로 볼지**(품질 규칙)·시나리오 | `data/eval/scenarios.json` |

3. `--compare before` — ▲ 는 좋아진 것, ▼ 는 나빠진 것, 그리고 **코스가 실제로 어떻게 바뀌었는지**(전/후 상호)가 나온다.
4. 좋아졌으면 `--save before` 로 기준선을 올리고, API 를 재시작해 서비스에 반영한다. 나빠졌으면 파일을 되돌린다.

> 주의: 한 지표를 올리면 다른 지표가 내려갈 수 있다(예산을 엄격히 하니 한 시나리오의 장소 수가 줄었다).
> 그래서 항상 **전체 점수표**로 판정한다 — 고친 그 한 건만 보지 않는다.

## 3. 지금 세는 결함 (= "서비스의 틀")

| 코드 | 뜻 |
|---|---|
| `NO_COURSE` · `FEW_STOPS` · `EMPTY_SLOT` | 코스를 못 만들었다 / 너무 짧다 / 필수 단계를 못 채웠다 |
| `CLOSED_AT_ARRIVAL` · `TOO_EARLY` | 도착 시각에 닫았을 곳(밤의 박물관·시장) / 아직 이른 곳(낮술) |
| `LONG_WALK` | 위저드가 약속한 "구간 20분 이내"를 넘는다 |
| `OVER_BUDGET` · `LOW_BUDGET_USE` | 예산 초과(컨셉 위반) / 예산의 45%도 못 씀 |
| `FAMILY_BAR` · `DATE_CHAIN` · `SNACK_AS_MEAL` | 목적에 안 맞는 선택 |
| `NOT_A_SIGN` · `VAGUE_SIGHT` | 법인 상호 / 지역명 그대로인 모호한 "명소" |
| `SAME_KIND_TWICE` | 같은 종류를 두 번 |
| (집계) 같은 명소에 기대는 지역 | 한 지역 코스의 절반 이상이 같은 명소 하나에 의존 |

새 규칙은 `harness.py › judge()` 에 몇 줄, 설명은 `CHECKS` 에 한 줄. 사용자가 "이건 어색하다"고 짚은 것은
**먼저 규칙으로 만들어 수치로 센 뒤** 고친다 — 그래야 다시 생기면 점수표가 알려 준다.

## 4. 첫 적용 기록 (2026-09-21)

| 조치 | 결함 없는 코스 |
|---|---|
| 시작 | 71.7% |
| 업종별 기본 영업시간(밤의 백화점·유적·박물관 차단) | 76.7% |
| + 선택 슬롯은 못 채워도 경고하지 않음 · 예산 초과 허용 105% → 100% · 데이트는 식사·카페 체인점 제외 | 87.5% |

자동 테스트(`pytest`)·E2E 가 "깨지지 않았는가"를 본다면, 이 점수표는 **"추천이 말이 되는가"**를 본다. 셋 다 통과해야 배포한다.
