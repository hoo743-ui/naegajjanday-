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
