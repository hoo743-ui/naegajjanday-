# 58 · 개념 점수표 기록

`eval-concept` 한 번 = 한 줄 (docs/58-concept-scorecard.md).
자동으로 덧붙는다 — 손으로 고치지 않는다.

| 실행 | 표본 | 커밋 | 코스 | 통과 | 가장 먼 지표 (값 / 목표) | 이전 대비 | 메모 |
|---|---|---|---|---|---|---|---|
| 2026-09-26 05:24 | quick | e25c3ca | 79 | 19/23 | date_scene_flag_rate 24.1% / 5.0%, night_violation_rate 12.5% / 3.0%, repeated_kind_rate 6.3% / 5.0% | – | 첫 기준선 |
| 2026-09-26 05:46 | quick | b435b4c | 79 | 20/23 | night_violation_rate 12.5% / 3.0%, repeated_kind_rate 6.3% / 5.0%, day_schedule_conflict_rate 3.6% / 3.0% | ▲date_scene_flag_rate ▲clean_rate | round1: date group spots — 고깃집 업종만으로 단체석 위주(0.8) 아님 → 0.6, 상호(회식·연회·단체)로만 0.9 |
| 2026-09-26 06:49 | quick | 121acd4 | 79 | 20/23 | night_violation_rate 12.5% / 3.0%, repeated_kind_rate 6.3% / 5.0%, day_schedule_conflict_rate 3.6% / 3.0% | – | loop |
| 2026-09-26 06:58 | quick | 121acd4 | 79 | 23/23 | – | ▲night_violation_rate | round2: night |
| 2026-09-26 10:29 | quick | 05bb20e | 118 | 26/26 | – | – | round3: first vs regular |
| 2026-09-26 14:11 | quick | 959da44 | 118 | 26/26 | – | – | backlog 9: "상시운영" 가게 ≠ 24시간 (Δ 0 — 로컬 DB 의 저장된 시간은 배포 때 rules/hours_text 가 다시 읽는다) |
| 2026-09-26 14:29 | quick | be32dac | 118 | 26/26 | – | – | backlog 6 · 10: 합쳐진 이름 정리 · 매일 영업시간 (Δ 0 — 이름은 배포 때 rules/place_names 가 바꾼다) |
| 2026-09-26 14:30 | quick | a302c6f | 118 | 26/26 | – | – | docs/59 #2 옵션을 결과 화면으로(엔진 변경 없음) |
| 2026-09-26 14:24 | quick | 959da44 | 144 | 28/28 | – | – | docs/59 #7 꼭 들를 곳: errand_leg · 끝나고 들르기 end pull (errand_toward_rate 69.2% → 92.3% vs errand7-before) |
| 2026-09-26 14:49 | quick | 959da44 | 118 | 28/28 | – | – | A: 자주 모드 긴 도보 · 닫힌 곳을 짝 표본에서 센다(regular_long_walk_rate · regular_schedule_rate). 지난 장소는 가까이 다른 곳이 없을 때만 다시(been_penalty 0.18), 간판 영업시간(롯데월드몰)을 채점기도 믿는다 |
