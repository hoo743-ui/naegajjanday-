# 58. 개념 점수표 — 앱이 컨셉 쪽으로 가고 있는지 재는 자 (2026-09-26)

> 창업자: "컨셉의 방향으로 앱을 계속 낫게 만드는 파이프라인." 그 파이프라인의 **자**가 이것이다.
> `eval-courses`(docs/18 · 29)는 "코스가 **고장** 났나?"(닫힌 곳 · 긴 구간 · 예산 초과)를 센다.
> `eval-concept` 는 "코스가 **약속한 하루**인가?"를 센다 — 명소 동네에 그 동네에 오는 이유가 있는지, 데이트 · 여행이 체인을 피하는지,
> 혼자의 밤에 한잔할 곳이 있는지, 아이와의 하루가 일찍 끝나는지, 기념일이 한 곳에 힘을 주는지, 돈을 쓰는지(docs/48 · 49 · 51).
> 세션 중 스크래치 스크립트 넷(local_audit · chain_audit · concept_date · concept_night)을 정식으로 옮기고 일반화했다(docs/51 F2).

## 1. 돌리는 법

```bash
cd apps/api
uv run python -m app.cli eval-concept                       # quick: 약 120코스(자주 짝 39 포함), 3~8분 (전국 로컬 DB)
uv run python -m app.cli eval-concept --sample full         # full: 약 350코스, 25분 안팎
uv run python -m app.cli eval-concept --save baseline       # 이 이름으로도 저장
uv run python -m app.cli eval-concept --compare baseline    # 직전 실행 대신 baseline 과 비교
uv run python -m app.cli eval-concept --focus chain_rate_travel --note "여행 체인 감점 0.2→0.4"  # 고친 뒤: SHIP / HOLD 판정
uv run python -m app.cli eval-concept --json out.json --no-log   # 실험(기록 안 남김)
```

- **실제 파이프라인**(`CourseService.dry_run`)을 한 세션 · 한 서비스 인스턴스로 돌린다. DB 는 **읽기만** 한다 — SQLite 연결마다
  `PRAGMA query_only=ON`, `busy_timeout=30000`, 그래도 `database is locked` 면 물러났다가 다시(최대 6번). 다른 적재 작업과 같이 돌아도 된다.
- 날짜는 **다음 토요일(이틀 이상 뒤)** — 매번 같은 요일이라 실행끼리 비교된다.
- 결과: `%LOCALAPPDATA%/naegajjanday/eval/concept/<시각>.json` + `latest.json`(+ `named/<이름>.json`). 전국 DB 가 있어야 나오는 숫자라 **로컬에만** 둔다.
  `NAEGAJJANDAY_EVAL_DIR` 로 폴더를 바꿀 수 있다.
- 한 줄 요약은 [58-concept-scorecard-log.md](58-concept-scorecard-log.md)에 자동으로 덧붙고, **커밋한다**(추세는 저장소에 남는다).

### 표본 (`app/evaluation/concept.py › build_sample`)

| 묶음 | quick | full | 재는 것 |
|---|---|---|---|
| hotspot | draws.json 명소 동네(먹거리 · 볼거리가 적힌 52곳) 중 13곳 × (데이트 점심 6만 · 친구 넷 저녁 10.8만 · 여행 오전 7.8만) | 52곳 × 넷(+ 데이트 저녁 8만) | 명물 · 체인 |
| solo_night | 8곳 × 혼자 3만 20:30 · 21:30 | 18곳 × 20:30 · 21:30 · 23:00 | 혼자의 늦은 저녁 · 밤 한잔 |
| date_scene | 4곳 × 설레는 사이 21:30 · 오래 만난 사이 15:00 · 기념일 18:30(10만) | 8곳 × 세 장면 × 18:30 · 21:30 | 데이트 장면 |
| family_scene | 4곳 × 아이와 18:30 · 부모님과 12:00 · 어른끼리 21:30 (셋 12만) | 8곳 × 넷(+ 아이와 12:00) | 가족 장면 |
| night | 4곳 × 데이트 · 친구 21:30 | 8곳 × 데이트 · 친구 · 여행 | 밤 규칙 |
| regular | hotspot 요청 하나하나를 `familiarity=regular` 로 한 번 더(짝). "가 본 적 있음" = 짝인 처음 코스의 장소를 뺀다 | 같음 | 처음 · 자주 (docs/59 #1) |
| errand | hotspot 의 데이트 점심 · 친구 저녁을 "끝나고 들르기"(볼일 30분, 동네 중심에서 동쪽 3 km)로 한 번 더 | 같음 | 꼭 들를 곳 (docs/59 #7) |

## 2. 지표 — 무엇을 지키려는 숫자인가

`regular_*` 다섯은 **짝 표본의 자주 쪽에서만**, `errand_*` 둘은 **errand 묶음에서만** 세고, 나머지 지표는 두 쪽을 보지 않는다(기본 숫자는 짝 표본이 생기기 전과 그대로 비교된다).

값이 목표 쪽에 있으면 ✓. **방향**: ≥ 는 높을수록, ≤ 는 낮을수록 좋다. 코스를 못 만든 요청은 `no_course_rate` 만 세고 나머지 지표의 분모에서 빠진다.
목표는 **지금 값에 맞춘 것이 아니라 문서가 약속한 것**에서 왔다 — 처음엔 여럿이 ✗ 인 게 정상이다. 목표를 바꾸려면 이 표와 `METRICS` 를 같이 고치고 이유를 적는다.

| 지표 | 목표 | 원칙 (인용) | 읽는 법 |
|---|---|---|---|
| `draw_rate` | ≥ 70% | "처음 온 사람이 '이 동네에 왔다'고 느끼게 … **꼭:** 동네 명물 또는 대표 볼거리 하나(지금 '명물 포함 60.7%' → 목표 90%)" (docs/48 §5) | hotspot 묶음 중 **그 동네에 정말 있는** 먹거리 · 볼거리(signature_service.curate 를 거친 `ctx.draw_words / draw_ids`)가 하나라도 든 코스. 90% 는 여행의 목표라, 데이트 점심 · 친구 저녁까지 섞인 이 묶음은 70% 로 시작 |
| `chain_rate_date` | ≤ 10% | "오래 만난 사이: … 익숙한 체인 강하게 피함" · "절대 안 됨: 단체석 위주 대형 호프" (docs/48 §1) | 데이트의 식사 · 카페 · 디저트 · 술집 중 `체인점` 태그 비율(**장소 단위**) |
| `chain_rate_friends` | ≤ 25% | "엔빵했을 때 누구도 부담스럽지 않다" (docs/48 §3) — 친구 모임엔 체인이 금기가 아니다. 다만 비체인 술집이 평균가 탓에 밀리는 편향(docs/51 A2)은 잰다 | 친구의 식사 · 카페 · 술집 중 체인 |
| `chain_rate_friends_cafe` | ≤ 25% | 같은 원칙 — 다만 카페는 친구끼리 앉아 떠드는 자리다. 2,000원대 체인이 44%(docs/59 #4) | 친구의 카페 · 디저트 중 체인(장소 단위). 카페가 없는 코스(저녁 → 산책 → 술집)는 분모에 없다 |
| `chain_rate_travel` | ≤ 5% | "전국 체인 거의 금지 … 체인 카페 · 체인 음식점(대안이 있으면)" (docs/48 §5) | 여행의 식사 · 카페 · 술집 중 체인 |
| `chain_ending_rate` | ≤ 5% | "닫기: 여운 … **가장 약한 장소로 끝내지 않는다**" (docs/48 §0-1) · 7-5 닫기 규칙 | 마지막 장소가 체인 · 무인 매장(`WEAK_ENDING`) |
| `solo_night_bar_rate` | ≥ 80% | "혼자 — **밤:** 혼술바 · 심야 영화 · 야경 산책" (docs/48 §4) · "혼자의 밤: 술집이 가격 상한에 걸려 0곳 → 걷기만" (docs/51 B3) | 혼자 · 21시 이후 코스 중 술집(BAR)이 있는 비율 |
| `solo_late_bar_rate` | ≥ 80% | 같은 원칙 — 엔진의 밤(21시~)이 되기 전인 20시대도 혼자의 저녁은 "닫기: 한잔"(docs/48 §4). "20:30 · 3만 원: 곱창 + 산책뿐"(docs/59 #5) | solo_night 묶음의 20:30 코스 중 술집(BAR)이 있는 비율 |
| `date_scene_flag_rate` | ≤ 5% | "절대 안 됨: 무인매장, 단체석 위주 대형 호프 · 고깃집, … 키즈 시설" · "기념일: 예산의 절반 이상을 한 끼(또는 한 잔)에" · 설레는 사이: 시끄러운 곳 피함 (docs/48 §1) | `DATE_GROUP_SPOT`(단체석 ≥ 0.8 인 식사 · 술집) · `DATE_KIDS_SPOT` · `DATE_UNMANNED` · `ANNIV_NO_SPLURGE`(가장 비싼 식사 · 술집 < 총액 35%) · `ANNIV_SNACK_MEAL` · `NEW_KARAOKE` 중 하나라도 |
| `family_scene_flag_rate` | ≤ 5% | "가장 체력이 약한 사람에게 속도를 맞추고 … 술집(아이와 · 부모님과), 긴 도보 구간, 오락실 · 노래방(부모님과), 밤 21시 이후 코스(아이와)" (docs/48 §2) | `FAMILY_DRINK` · `FAMILY_BAR` · `KIDS_SPICY` · `KIDS_LATE`(마지막 장소를 21시 넘어 떠남) · `PARENTS_NOISY` · `LONG_LEG_KIDS/PARENTS`(20분 넘는 구간). 장면이 없으면 아이와(§9 결정) |
| `night_violation_rate` | ≤ 3% | "밤(21시~): 한잔 → 걷기. 2곳이 정상" · "닫힌 곳, 밤의 산길" (docs/48 §1 · 7-6) · "밤 데이트 = 술집"(팀원 피드백 2026-09-24) | 21시 이후 시작한 코스 중 `CLOSED_AT_ARRIVAL` · `NIGHT_TRAIL` · `TOO_EARLY` · `NIGHT_NO_DRINK`(데이트 · 친구의 밤에 술집 없음) · `DATE_UNMANNED` · `FAMILY_DRINK` |
| `cafe_cafe_rate` | ≤ 3% | "같은 종류 반복(카페 → 카페)" 은 데이트의 '절대 안 됨' (docs/48 §1) · 잔여 결함 "카페 → 디저트 반복 38/448" (docs/51 B4) | 카페 · 디저트가 연달아(경험 종류 CAFE 두 번 연속) |
| `low_budget_use_rate` | ≤ 10% | "예산은 약속이다. 약속한 돈의 1/4 만 쓴 코스를 설명 없이 내미는 것은 약속을 어긴 것과 같다" (docs/49) | **낮** 코스 중 예산 45% 미만(`LOW_BUDGET_USE`). 밤은 뺀다 — "밤 10시 이후라 이 근처에 연 곳이 많지 않아요"가 이미 설명된 남은 돈(docs/49 §2) |
| `over_budget_rate` | ≤ 0% | 같은 약속의 반대편: 예산을 넘는 코스는 없어야 한다 | `OVER_BUDGET`. 가중치 1.5 |
| `no_course_rate` | ≤ 2% | "밤에 앱을 여는 사람에게 '없어요'는 가장 나쁜 답" (밤 코스 결정 2026-09-22) | 코스를 못 만든 요청(오류 코드는 예시 줄에). 가중치 1.5 |
| `mean_stops_day` | ≥ 3.0 | "개수보다 밀도" (docs/48 §0-2) — 그래서 **바닥**만 본다. 늘리라는 지표가 아니다 | 낮 코스의 평균 장소 수 |
| `few_stops_rate` | ≤ 5% | 같은 원칙: 밤 2곳은 정상, 낮 3곳 미만은 결함(`scenarios.json › min_stops · min_stops_night`) | `FEW_STOPS`. 아이와의 저녁(17시 이후 시작)은 뺀다 — 20:30 에 끝내는 장면(`scenes.json › end_by`)이라 2곳이 약속대로다 |
| `empty_slot_rate` | ≤ 10% | "없느니만 못한 장소는 비운다" (docs/48 §0-3) — 비우는 건 괜찮지만 너무 잦으면 후보가 모자란 것 | `EMPTY_SLOT` |
| `day_schedule_conflict_rate` | ≤ 3% | 닫힌 곳에 데려가지 않는다 (eval-courses) | 낮 코스의 `CLOSED_AT_ARRIVAL` · `TOO_EARLY` · `NIGHT_TRAIL` |
| `long_walk_rate` | ≤ 10% | "구간 20분 이내" 약속, v2 는 30분 넘는 구간만 결함 (eval-courses) | `LONG_WALK` |
| `snack_as_meal_rate` | ≤ 3% | "간편식을 식사로" 는 데이트의 '절대 안 됨', 가족은 "모두가 앉을 수 있는 식사 한 번" (docs/48 §1 · §2) | 데이트 · 가족의 식사 자리가 분식 · 간식(`SNACK_AS_MEAL`) |
| `repeated_kind_rate` | ≤ 5% | "같은 종류 반복" (docs/48 §1) | 같은 경험을 허용보다 많이(`REPEATED_KIND`) |
| `same_kind_twice_rate` | ≤ 10% | 같은 원칙, 업종 코드 단위 — 점심 · 저녁 한식 두 번처럼 괜찮은 경우가 있어 느슨하게 | `SAME_KIND_TWICE` |
| `naming_rate` | ≤ 2% | "지어내지 않는다 … 간판" (docs/54 §5) — 이름이 모호하면 사람이 찾아가지 못한다 | `VAGUE_SIGHT` · `NOT_A_SIGN` |
| `clean_rate` | ≥ 50% | 모든 규칙을 합친 한 숫자 | 어떤 플래그도 없는 코스. 가중치 0.5 — 다른 지표를 고치면 따라 오른다. 직접 고칠 대상이 아니다 |
| `regular_draw_rate` | ≤ 50% | "처음 오는 사람은 그 지역의 특색 … 많이 오는 사람들은 어차피 거기서 거기" (창업자 2026-09-26, docs/59 #1) | **짝 표본**. 자주 모드 코스 중 명물(★)이 든 코스 수 ÷ 짝인 처음 모드 코스 중 명물이 든 코스 수 — 처음의 절반 아래로 |
| `regular_overlap_rate` | ≤ 20% | 같은 원칙: 자주 오는 사람에게 같은 곳을 다시 내밀지 않는다 | 자주 모드 코스의 장소 중 짝인 처음 코스와 겹치는 곳(같은 id 또는 같은 간판 — 중복 등록도 같은 곳) |
| `errand_toward_rate` | ≥ 80% | "끝나고 들르기: 마지막 장소를 그쪽으로" (docs/59 #7) | **errand 묶음**. 마지막 장소가 코스에서 볼일에 가장 가까운 장소보다 300 m 넘게 멀지 않은 코스(볼일 반대편에서 끝나지 않는다). 예시 줄 끝의 `볼일(N분, …m 멀리서 끝남)` |
| `errand_leg_rate` | ≥ 95% | "먼저 들르기: 그곳에서 오는 경로가 지도에 없다" (docs/59 #7) | errand 묶음 코스 중 볼일 ↔ 코스 구간(시간 · 거리 — 지도에 그리는 `errand_leg`)이 있는 것 |
| `regular_novelty_rate` | ≥ 50% | 같은 원칙: 안 가 본 곳 · 새로 생긴 곳 · 덜 알려진 곳 | 자주 모드 코스의 장소 중 새로 생긴 독립 가게(인허가일자 2년 안) 또는 덜 알려진 독립 가게(체인 · 무인 · 공공 소개 · 티맵 인기 · 동네 명물이 아닌 곳). 예시 줄의 `✧` |
| `regular_long_walk_rate` | ≤ 10% | `long_walk_rate` 와 같다 — 가 본 곳을 빼느라 35분을 걷게 하면 안 된다 | **짝 표본**의 자주 쪽에서 `LONG_WALK`. 가 본 곳은 짝인 처음 코스의 장소를 로그인 사용자의 기록처럼(`dry_run(been=…)`) 넘긴다 — 사용자의 "이곳 빼 줘"(exclude)와 달리 가까이 다른 곳이 없으면 다시 들어올 수 있다 |
| `regular_schedule_rate` | ≤ 3% | `day_schedule_conflict_rate` 와 같다 | 짝 표본 자주 쪽 낮 코스의 `CLOSED_AT_ARRIVAL` · `TOO_EARLY` · `NIGHT_TRAIL` |

### 순위 — "가장 나쁜" 지표

`gap = 가중치 × (목표를 넘어선 만큼) / scale`. scale 은 비율 지표 0.25(25%p 모자라면 1.0), 평균 장소 수 1.0곳.
✗ 인 지표를 gap 이 큰 순서로, 그다음 ✓ 인 지표를 목표에 가까운 순서로 보여 준다. 분모가 0 인 지표(그 묶음이 표본에 없음)는 맨 아래 `–`.
실패한 지표마다 **예시 코스 3~5줄**(동네가 겹치지 않게 먼저 고른다): `동네|목적/장면|시작|예산 → 쓴 돈 | 시각 자리 이름 …  [걸린 규칙]`.
`ⓒ` = 체인, `★` = 그 동네에 오는 이유.

### 잡음 범위 · Δ

한 번의 실행은 결정적이다(같은 DB · 같은 표본 · 같은 요일). 그래도 표본은 전체의 일부라, 코스 한두 개가 바뀌어 움직이는 숫자는 개선도 회귀도 아니다.
잡음 범위 = 표준오차의 1.5배, 비율은 최소 2%p(평균은 0.1). Δ 옆 `▲` 나아짐 · `▼` 나빠짐(범위 밖), `·` 범위 안.

## 3. 개선 루프

자동 루프(몇 시간마다)와 사람이 똑같이 따른다.

1. **잰다.** `eval-concept`(quick). 맨 위의 ✗ 지표와 예시 줄을 본다.
2. **고른다.** 가장 나쁜 지표 중 **다른 작업자가 이미 고치고 있지 않은 것**(열린 워크트리 · 최근 기록의 메모를 본다).
   데이터가 없어서 생기는 것(예: 영업시간 0.1%, 실측 가격 4% — docs/51 A1 · A2)은 엔진으로 억지로 맞추지 말고 데이터 작업으로 넘긴다.
3. **워크트리에서 고친다.** 규칙 · 가중치 데이터(`data/recommendation/*.json`, `data/regions/draws.json`)가 먼저, 코드는 그다음.
   예시 줄이 왜 그렇게 나왔는지부터 확인한다(한 코스의 원인이 지표 전체의 원인이 아닐 수 있다).
4. **다시 잰다.** `eval-concept --focus <지표> --note "<무엇을 바꿨나>"`.
   **SHIP** 은 그 지표가 나아졌고, **다른 어떤 지표도 잡음 범위 밖으로 나빠지지 않았을 때만**. 아니면 HOLD — 되돌리거나 다시 고친다.
   판정은 직전 실행과 비교한다. 워크트리의 첫 실행이 기준이 되게 하려면 고치기 전에 한 번 `--save before` 하고 `--compare before`.
5. **기록한다.** 실행마다 `58-concept-scorecard-log.md` 에 한 줄이 붙는다(메모 = 무엇을 고쳤나). 고친 코드 · 데이터와 그 줄을 **같은 커밋**으로 낸다.
   목표를 바꿨다면 이 문서의 표도 같이.

한 번에 지표 하나. 여러 지표를 한꺼번에 움직이는 변경은 어느 것이 무엇을 했는지 알 수 없다.

## 4. 코드

- `apps/api/data/eval/concept.json` — 장면 · 밤 묶음의 동네(코드에 동네 이름을 두지 않는다 — `test_no_region_or_place_names_are_hardcoded_in_python`).
- `apps/api/app/evaluation/concept.py` — 표본 · 기록(`Case` · `Stop` · `Record`) · 개념 규칙(`concept_flags`) · 지표(`METRICS`) · 순위 · 비교 · 저장.
  규칙과 지표는 DB 없이 평범한 기록 위에서 돌아가서 `tests/unit/test_concept_scorecard.py` 가 가짜 코스로 검사한다.
- 코스마다 붙는 판정은 두 곳에서 온다: `harness.judge`(eval-courses 와 같은 규칙, `data/eval/scenarios.json`) + `concept_flags`(docs/48 의 목적 · 장면 규칙).
- 명소 판정은 `draws.json` 원문이 아니라 **그 동네에 정말 있는 것만 남긴** 목록(`ctx.draw_words / draw_ids`)으로 한다 — 없는 명물로 동네를 탓하지 않는다.
- CLI: `app/cli.py › eval-concept`.
