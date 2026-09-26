# 62. 사용 지표 — 1자 이벤트와 "쓰인 코스" 비율 (2026-09-26)

docs/61 §7 권고 1번. 운영 웹 번들에는 GA4 · PostHog · Mixpanel 키가 없어서 `track()` 이벤트가 **아무 데도 쌓이지 않았다**. 이제 `track()` 은 늘 우리 API 로도 보내고, 관리자 **분석 → 사용 지표**(`/admin/usage`)와 대시보드 카드, CLI 가 같은 숫자를 보여 준다. 외부 도구는 키를 넣으면 그대로 함께 받는다.

## 흐름

| 곳 | 무엇 |
|---|---|
| `apps/web/src/lib/analytics/first-party.ts` | `track()` 이 부를 때마다 큐에 넣고 20개 또는 4초마다 `POST /v1/events`(`fetch keepalive`, 로그인이면 토큰), 페이지를 떠날 때(`pagehide` · 숨김) `navigator.sendBeacon`(`text/plain` — CORS 사전 요청 없음, 토큰 없음 → 그 묶음은 계정 없이). 실패하면 버린다. DNT · GPC · `localStorage["njd.analytics_optout"]="1"` · 목(mock) 모드 · `/admin` 에서는 보내지 않는다 |
| `apps/api/app/api/v1/events.py` | 본문을 content-type 과 상관없이 JSON 으로 읽는다. 32KB · 50개까지. **카탈로그에 없는 이름만 있으면 422**, 섞여 있으면 아는 것만 저장하고 `202 {"accepted","dropped","unknown"}`. `DNT: 1` · `Sec-GPC: 1` · 봇 UA → 204(저장 안 함). 속도 제한: IP 600/분(`RL_EVENTS_IP`, 캠퍼스 NAT), 브라우저 60/분(`RL_EVENTS_DEVICE`) |
| `apps/api/app/services/event_catalog.py` | 이벤트 이름과 이벤트별 허용 속성. 문자열은 64자까지(넘으면 자르지 않고 버린다), 숫자 · 참거짓만. 웹 `events.ts` 에 새 이벤트를 더하면 여기에도 더한다 |
| 표 `app_event` (Alembic 0014) | name · device(=`visit.visitor` 와 같은 HMAC 해시) · user_id · course_id · path(쿼리 없이) · props · created_at(브라우저 시각, 하루 이상 어긋나면 서버 시각). IP · UA · 자유 글 없음 |

SQLite(Render)는 `db init`(create_all)이 표를 만든다. Postgres 는 `alembic upgrade head`.

## 이벤트

"쓰인 코스"에 들어가는 것

| 신호 | 이벤트 |
|---|---|
| 저장 | `course_saved` + `course.status` ∈ saved · shared · completed |
| 공유 | `share_clicked` (· `course_shared`) |
| 길찾기 · 바깥 링크 | `directions_opened` · `place_link_clicked` · `outbound_link` |
| 확정 · 다녀옴 | `course_confirmed` · `visit_marked`(이번에 추가: "다녀왔어요") + `course_feedback.visited` |

바꾸기 = `stop_swapped` · `stop_swapped_from_sheet`. 다시 짜기 = `reroll_clicked` · `reroll_tweaked` · `course_settings_changed` · `course_option_toggled` · `familiarity_changed`. 스톱 시트 이벤트(`stop_sheet_opened` · `stop_fixed` · `stop_alternative_viewed` · `stop_swapped_from_sheet` · `course_confirmed` · `outbound_link`)는 웹에 붙기 전에 허용 목록에 먼저 넣었다(속성은 position · category · role · to · from · via · kind · pinned · fixed · rank · strategy).

## North star — 쓰인 코스 비율 (주간)

단위는 **코스를 만든 번** = `recommendation_log` 한 줄(주 코스 + 대안). `course` 는 저장 안 된 코스를 24시간 뒤 지우므로 분모로 못 쓴다. 한 번이 7일 안에 위 신호 중 하나라도 가지면 "쓰였다". 주는 한국 날짜 월요일부터, 최근 8주, 그 주 마지막 날 + 7일이 안 지났으면 "집계 중".

```sql
-- 참고용 (실제 계산은 services/usage_metrics.py 의 compute(), 단위 테스트 있음)
WITH gen AS (
  SELECT l.id, l.created_at, json_extract(c.value, '$.course_id') AS course_id
  FROM recommendation_log l, json_each(l.selected_courses) c
  WHERE l.created_at >= :since
), used AS (
  SELECT DISTINCT g.id FROM gen g
  JOIN app_event e ON e.course_id = g.course_id
   AND e.name IN ('course_saved','share_clicked','course_shared','directions_opened',
                  'place_link_clicked','outbound_link','course_confirmed','visit_marked')
   AND e.created_at BETWEEN g.created_at AND datetime(g.created_at, '+7 days')
  UNION
  SELECT g.id FROM gen g JOIN course c ON c.public_id = g.course_id
   WHERE c.status IN ('saved','shared','completed')
)
SELECT date(l.created_at, 'weekday 1', '-7 days') AS week,  -- 대략의 월요일 (UTC)
       count(*) AS generated, count(u.id) AS used
FROM recommendation_log l LEFT JOIN used u ON u.id = l.id
WHERE l.created_at >= :since GROUP BY week ORDER BY week;
```

## 사용자 가치 지표 (기간: 기본 28일)

| 지표 | 정의 |
|---|---|
| 첫 코스 채택 | 쓰인 번 중 (a) 그 코스들에 바꾸기 · 다시 짜기 이벤트가 없고 (b) 같은 브라우저가 30분 안에 다시 짜기를 누른 뒤 만든 번이 아닌 비율. 브라우저는 그 번의 `course_generated` 이벤트로 안다 |
| 업종별 바꾸기 | 이벤트가 하나라도 잡힌 코스의 칸을 업종(카테고리 코드 앞부분)별로 세고, 바꾸기 이벤트의 position 을 **만들 때의** 장소에 맞춰 센다(두 번째 바꾸기도 처음 장소의 업종으로 — 근사) |
| 옵션 칩 | `course_option_toggled` 옵션별 켬 · 끔 · 칩 · 한 줄 말 · 설정, 한 줄 말(`course_option_text_parsed`) 중 하나라도 알아들은 비율. 말 자체는 받지 않는다 |
| 바깥 링크 | 길찾기 · 장소 링크가 열린 번 ÷ 만든 번 |
| 공유 → 열림 | 공유 이벤트가 있는 코스 중 `/course/{id}` 방문(`visit`)이 공유한 브라우저가 아닌 곳에서 있었던 비율 |
| 다녀옴 · 예산 정확도 | `course_feedback` 의 visited, 실제 지출이 코스 금액 ±20% 안 |
| 이벤트가 잡힌 번 | 수집이 도는지 보는 값. 광고 차단기 · DNT 가 많으면 낮다 — 이 비율로 위 지표를 읽는다 |

같은 숫자: 관리자 `GET /v1/admin/analytics/usage-metrics?days=28`, `python -m app.cli usage-report --days 28`(Render Shell).

## 보관 · 개인정보

- `app_event` 는 **180일**(`EVENT_RETENTION_DAYS`) 뒤 API 시작 때마다 지운다(`retention.purge_old_events`). 탈퇴 계정의 이벤트는 user_id 를 비운다.
- 개인정보처리방침(`/privacy`)에 "코스 화면을 쓸 때" 줄 · 180일 · DNT/GPC 를 적었다.
- 수집 전 기간의 비율은 저장(상태) · 다녀옴만 센다 — 관리자 화면이 "이벤트 수집 시작일"을 함께 보여 준다.

## 한계

- 저장 시각을 따로 두지 않아 `course.status` 저장은 7일 창과 관계없이 센다.
- sendBeacon 묶음(페이지를 떠날 때)은 토큰이 없어 계정 없이 저장된다. 지표는 코스 · 브라우저 기준이라 영향 없다.
- 관리자 · 평가 스크립트가 만든 코스도 `recommendation_log` 에 있다 — 분모에 들어간다.
