# 03. API 명세

> Base URL `https://api.naegajjanday.com/v1` · JSON · UTF-8 · 시간은 ISO-8601(+09:00) · 금액은 원(KRW) 정수
> FastAPI가 생성하는 OpenAPI(`/v1/openapi.json`, `/v1/docs`)가 **정본**이고, 이 문서는 설계 의도와 규약을 설명한다. 프론트 타입은 `openapi-typescript`로 자동 생성한다.

## 1. 공통 규약

### 인증
| 방식 | 대상 | 헤더 |
|---|---|---|
| 없음 | 메타 조회, 코스 생성(비로그인 허용, rate limit 엄격) | — |
| JWT Access (15분) | 사용자 API | `Authorization: Bearer <access>` |
| Refresh (14일, rotation) | 토큰 갱신 | `HttpOnly; Secure; SameSite=Lax` 쿠키 `rt` |
| JWT + `role ∈ {admin, operator}` | `/admin/*` | 동일 + 관리자 IP allowlist(WAF) |

### 에러 포맷 (RFC 9457 Problem Details)
```json
{
  "type": "https://api.naegajjanday.com/errors/budget-too-low",
  "title": "예산이 너무 낮아요",
  "status": 422,
  "code": "BUDGET_TOO_LOW",
  "detail": "홍대입구에서 2명 기준 최소 12,000원이 필요해요.",
  "meta": { "min_budget": 12000 },
  "trace_id": "01J9..."
}
```
`code`는 프론트에서 짠이 표정·문구를 고르는 키로 쓴다 (`BUDGET_TOO_LOW` → `jj-sorry`).

### 페이지네이션 · Rate Limit
- 커서 기반: `?cursor=<opaque>&limit=20` → `{ "items": [...], "next_cursor": "..." | null }`
- 응답 헤더 `X-RateLimit-Limit / Remaining / Reset`, 초과 시 `429` + `Retry-After`

| 스코프 | 한도 |
|---|---|
| 비로그인 IP — `POST /courses/generate` | 10 / 시간 |
| 로그인 사용자 — 코스 생성 | 60 / 시간 |
| 챗봇 메시지 | 30 / 시간 |
| 그 외 읽기 | 300 / 분 |

### 멱등성
`POST` 생성 계열은 `Idempotency-Key` 헤더 지원 (Redis 24h).

---

## 2. 메타 (전부 DB 기반 — 지역 추가 시 코드 수정 없음)

| Method | Path | 설명 |
|---|---|---|
| GET | `/meta/regions?parent=seoul&q=홍대` | 활성 지역 트리/검색 |
| GET | `/meta/purposes` | 목적 목록 + 아이콘 + 추천 예산 범위 |
| GET | `/meta/categories` | 카테고리 트리 |
| GET | `/meta/tags?group=mood` | 선호 태그 칩 |
| GET | `/meta/banners?placement=home&region=seoul-hongdae` | 노출 중 배너 |

```jsonc
// GET /meta/regions
{ "items": [
  { "slug": "seoul-hongdae", "name": "홍대입구", "level": 3,
    "center": { "lat": 37.5572, "lng": 126.9245 }, "radius_m": 1200,
    "parent": { "slug": "seoul-mapo", "name": "마포구" }, "place_count": 1284 }
]}
```

## 3. 코스 추천 (핵심)

### `POST /courses/generate`
```jsonc
// Request
{
  "region": "seoul-hongdae",          // 또는 "origin": {"lat":..,"lng":..}
  "purpose": "date",
  "party_size": 2,
  "budget_total": 40000,
  "start_at": "2026-09-20T18:00:00+09:00",   // 생략 시 now
  "duration_min": 240,                 // 선택(60~960). 주면 그 시간에 맞춰 슬롯 수·체류 시간을 조절하고 warnings 에 DURATION_FIT 안내가 붙는다. 330 이상 + 15시 전 시작 → fullday 템플릿
  "style": "efficient",               // 선택. efficient(기본) | fun(북적이는 거리·놀거리 위주, 식사·카페 체인점 제외)
  "transport": "walk",                 // walk | transit | car
  "include_roles": ["MEAL","CAFE","ATTRACTION","BAR"],  // 선택, 생략 시 템플릿
  "preferences": { "liked_tags": ["조용한","뷰맛집"], "disliked_tags": ["웨이팅"], "exclude_place_ids": [] },
  "alternatives": 2
}
```
```jsonc
// 200 Response
{
  "request_id": "01J9ZK…",
  "courses": [{
    "id": "c0a8…",                     // public_id (저장 전에는 임시, 24h 캐시)
    "label": "추천 코스",               // | "가성비 코스" | "덜 걷는 코스"
    "summary": "둘이서 36,000원, 걸어서 18분이면 충분해요",
    "totals": { "price": 36000, "price_per_person": 18000, "budget_left": 4000,
                "budget_utilization": 0.9, "travel_min": 18, "distance_m": 1320,
                "duration_min": 225, "score": 0.82 },
    "stops": [{
      "position": 1, "role": "MEAL",
      "place": { "id": "p_9f…", "name": "…", "category": "food.korean", "lat": 37.55, "lng": 126.92,
                 "address": "…", "thumbnail_url": "…", "rating": 4.5, "review_count": 812,
                 "price_per_person": 12000, "tags": ["가성비","조용한"] },
      "arrive_at": "2026-09-20T18:05:00+09:00", "leave_at": "2026-09-20T19:05:00+09:00",
      "est_price": 24000,
      "from_prev": { "travel_min": 5, "distance_m": 350, "mode": "walk" },
      "score": 0.86,
      "score_breakdown": { "budget": 0.95, "distance": 0.81, "rating": 0.78, "sentiment": 0.84,
                           "congestion": 0.6, "time_fit": 0.9, "preference": 0.7, "purpose_fit": 0.8 },
      "reason": "예산에 딱 맞고, '조용해서 대화하기 좋다'는 리뷰가 많아요",
      "congestion": { "level": "보통", "value": 0.4 }
    }],
    "route": { "polyline": "encoded…", "optimizer": "held_karp" },
    "warnings": []
  }],
  "nearby_events": [ { "id": "e_…", "title": "…축제", "ends_on": "2026-09-28", "distance_m": 640, "is_free": true } ],
  "meta": { "engine_version": "1.0.0", "scoring_profile": "date@v3", "candidates": 214, "latency_ms": 612 }
}
```
| 상태 | code | 상황 |
|---|---|---|
| 422 | `BUDGET_TOO_LOW` | 최소 템플릿 예산 미달 (`meta.min_budget` 제공) |
| 404 | `REGION_NOT_FOUND` / `REGION_NOT_READY` | 지역 없음 / 수집 중 |
| 200 + `warnings` | `SLOT_EMPTY` | 일부 슬롯 후보 없음 — 부분 코스 반환 |

### 코스 후속 API
| Method | Path | 설명 |
|---|---|---|
| POST | `/courses/{id}/swap` | 특정 스톱만 교체 `{ "position": 2, "strategy": "cheaper|closer|higher_rated|random_top" }` → 나머지 고정하고 재최적화 |
| POST | `/courses/{id}/reorder` | 사용자가 드래그로 순서 변경 → 이동시간·도착시각 재계산 |
| GET | `/courses/{id}/narrative` | **SSE 스트림** — LLM 설명을 토큰 단위로 (코스 생성 응답을 막지 않기 위해 분리) |
| POST | `/courses/{id}/save` 🔒 | 내 코스로 저장 |
| GET | `/courses/{id}` | 공유 링크 조회 (OG 메타 포함) |
| GET | `/me/courses` 🔒 | 내 코스 목록 |
| DELETE | `/me/courses/{id}` 🔒 | |
| POST | `/courses/{id}/feedback` 🔒 | `{ rating, visited, actual_spend, stop_feedback:[{position, liked}] }` → 선호도 학습 |

## 4. 장소 · 탐색

| Method | Path | 설명 |
|---|---|---|
| GET | `/places/search?q=&region=&role=&max_price=&lat=&lng=&radius=&sort=` | Elasticsearch (nori, geo_distance) |
| GET | `/places/autocomplete?q=홍대 파` | edge-ngram, 50ms 목표 |
| GET | `/places/{id}` | 상세: 메뉴, 영업시간, 혼잡도 24h, 감성 aspect, 리뷰 요약 |
| GET | `/places/{id}/nearby?role=CAFE` | 주변 추천 |
| GET | `/attractions?region=&type=park,exhibition,festival,culture&date=` | 관광지·공원·전시·축제·문화공간 통합 |
| GET | `/events?region=&from=&to=` | 기간 내 이벤트 |
| POST | `/places/suggest` 🔒 | 사용자 장소 제보 → `pending` 큐 |

## 5. 인증 · 사용자

| Method | Path | 설명 |
|---|---|---|
| GET | `/auth/{provider}/login` | `kakao` `naver` `google` — OAuth2 Authorization Code + PKCE, `state` 검증 |
| GET | `/auth/{provider}/callback` | 토큰 교환 → 사용자 upsert → access 발급 + refresh 쿠키 |
| POST | `/auth/refresh` | Refresh rotation. 재사용 탐지 시 토큰 패밀리 전체 폐기 |
| POST | `/auth/logout` | refresh 폐기 + access `jti` denylist |
| GET / PATCH | `/me` 🔒 | 프로필 |
| GET / PUT | `/me/preferences` 🔒 | 선호 태그·카테고리·이동수단 |
| DELETE | `/me` 🔒 | 탈퇴(30일 유예 후 파기, 개인정보보호법) |

## 6. AI 챗봇 (짠이)

| Method | Path | 설명 |
|---|---|---|
| POST | `/chat/sessions` | 세션 생성 |
| POST | `/chat/sessions/{id}/messages` | **SSE**. `{ "content": "성수에서 3만원으로 혼밥하고 전시 볼래" }` |

챗봇은 LLM **tool-use**로 동작한다. 모델이 직접 장소를 지어내지 않고 아래 도구만 호출한다 → 환각 방지.
`generate_course(params)` · `search_places(query)` · `swap_stop(course_id, position, strategy)` · `get_events(region, date)`

SSE 이벤트: `token`(텍스트) · `tool_call` · `course`(코스 카드 payload) · `done` · `error`

## 7. 관리자 API (`/admin/*`, role 필요, 전부 `audit_log` 기록)

| 영역 | Endpoints |
|---|---|
| 장소 승인 | `GET /admin/places?status=pending` · `POST /admin/places/{id}/approve` · `/reject` · `POST /admin/places/bulk-approve` |
| 장소 수정 | `PATCH /admin/places/{id}` · `POST /admin/places/{id}/merge` (중복 병합) · `GET /admin/places/{id}/revisions` |
| 관광지 추가 | `POST /admin/places` (category role = ATTRACTION/CULTURE) · `POST /admin/places/import` (CSV/JSON 업로드 → `file` provider 잡) |
| 이벤트 | `GET/POST/PATCH/DELETE /admin/events` |
| 배너 | `GET/POST/PATCH/DELETE /admin/banners` · `POST /admin/uploads/presign` (S3 presigned URL) |
| **지역** | `GET/POST/PATCH /admin/regions` · `POST /admin/regions/{slug}/collect` (수집 잡 트리거) · `POST /admin/regions/{slug}/activate` |
| 추천 설정 | `GET/PUT /admin/scoring-profiles/{purpose}` · `GET/POST/PATCH /admin/templates` · `GET/PUT /admin/purposes/{code}/tag-affinities` |
| 수집 | `GET /admin/ingestion/jobs` · `POST /admin/ingestion/jobs` · `POST /admin/ingestion/jobs/{id}/retry` |
| 사용자 분석 | `GET /admin/analytics/users?from=&to=` (DAU/WAU, 리텐션 코호트, 유입) |
| 추천 통계 | `GET /admin/analytics/recommendations` (생성 수, 저장률, 재추천률, 평균 예산, 지역×목적 히트맵, 슬롯 공백률, p95 지연) · `GET /admin/analytics/places/top` |
| 시스템 | `GET /admin/system/health` · `POST /admin/cache/invalidate` · `POST /admin/search/reindex` |

## 8. 내부 · 운영

| Path | 설명 |
|---|---|
| `GET /healthz` | liveness |
| `GET /readyz` | DB·Redis·ES 연결 확인 (ALB 헬스체크) |
| `GET /metrics` | Prometheus (내부망 전용) |
| `POST /internal/webhooks/ingestion` | 배치 완료 콜백 (서명 검증) |

## 9. 버저닝 · 호환성

- URL 메이저 버전(`/v1`). 필드 추가는 하위호환으로 간주, 삭제·의미 변경은 `/v2`.
- Deprecation: `Deprecation`, `Sunset` 헤더 + 최소 90일 병행.
- 계약 테스트: CI에서 `schemathesis`로 OpenAPI 대비 실제 응답 검증, 프론트는 생성된 타입으로 컴파일 타임 검증.


## 길찾기 (지도 표시용) — `/directions`

결과 화면의 **실제 지도·실제 보행 경로·대중교통 접근 안내**를 위한 표시 전용 API. 스코어링·경로 최적화에는 쓰지 않는다(그쪽은 `travel_time` 공급자). 이 API 가 죽어도 코스는 그대로 나오고, 지도 선만 직선으로 떨어진다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/directions/walk?points=lat,lng;lat,lng;…` | 방문 순서대로 이은 보행 경로. `source: "osrm"`(실제 길) 또는 `"straight"`(폴백). `coordinates` 는 `[lat, lng]` 배열, `legs[i]` 는 i→i+1 구간의 거리·시간 |
| GET | `/directions/access?points=…` | 지점별 가장 가까운 **지하철 출구(역명·출구 번호)** 와 **버스 정류장**, 각각 직선거리·도보 분 |

- 보행 경로: OSRM 호환 라우터(`OSRM_FOOT_URL`, 기본값은 공개 FOSSGIS 서버·키 불필요·공정 이용). 운영에서는 한국 추출본으로 자체 OSRM 을 띄워 이 값만 바꾼다. 타임아웃 `DIRECTIONS_TIMEOUT_S`(4초), 프로세스 내 LRU 캐시 512건.
- 접근 안내: OpenStreetMap 추출본 `apps/api/data/transit/*.tsv` (지하철 출구 4,500 · 역 1,321 · 버스 정류장 100,642, 2026-09-21 추출). **ODbL** 이므로 자체 장소 테이블과 병합하지 않고 별도 파일로 두며 화면에 출처를 표기한다. 갱신은 Overpass 재추출.
- 지도: 웹은 `NEXT_PUBLIC_KAKAO_MAP_KEY` 가 있으면 카카오맵, 없으면 Leaflet + OpenStreetMap 타일(키 불필요), 타일도 못 받으면 SVG 약도 순으로 떨어진다. 운영 트래픽에서는 OSM 공용 타일 대신 타일 공급자(또는 카카오맵 키)를 쓴다.
- 환승 노선·실시간 도착 같은 상세 대중교통 안내는 구간별 **카카오맵 길찾기 링크**(`map.kakao.com/link/by/{walk|traffic|car}/…`)로 넘긴다. 앱 내 환승 경로가 필요해지면 ODsay·TMAP 대중교통 API(키 필요) 어댑터를 같은 자리에 붙인다.

## 부록: 2026-09-21 에 늘어난 요청 · 응답 (코스 생성)

`POST /v1/courses/generate` 에 아래 필드가 추가됐다. 모두 선택이고, 안 주면 예전과 똑같이 동작한다.

| 필드 | 뜻 |
|---|---|
| `purposes: string[]` | 함께 고른 다른 목적(최대 3). 첫 목적(`purpose`)이 하루의 틀을, 모든 목적이 가중치 · 취향을 정한다. 한 목적의 금기(가족 → 술집)는 전체에 적용 |
| `regions: string[]` | 여러 동네를 잇는다(당일 최대 3). 예산 · 시간을 나눠 쓰고 남은 돈은 다음 동네로. 응답 스톱의 `from_prev.hop_to` 가 동네 이동 구간 |
| `nights: 0~3` | 몇 박. 날짜별 코스가 `1일차 · 2일차 …` 라벨로 온다(상세의 `siblings` 가 탭). 상세 `request.day / days / trip_budget_total` |
| `focus: string` | 꼭 넣을 동네 명물(`GET /v1/meta/regions/{slug}/signature` 의 word). 생략 = 가장 뚜렷한 명물을 자동으로, `"-"` = 넣지 않음. 못 넣으면 경고 `FOCUS_UNAVAILABLE` |
| `extras: string[]` | 꼭 넣을 자리. `BAR`(술 한잔), `BASEBALL`(1군 구장 — 요청했을 때만 후보가 된다) |
| `conditions: string[]` | 그날의 사정. `rain` = 실내 위주 |
| `skip_roles: string[]` | 코스에서 뺄 자리 |

새 엔드포인트: `GET /v1/meta/regions/{slug}/signature` · `GET /v1/stays?lat&lng&radius_m&limit` · `GET /v1/performances?lat&lng&start_at&duration_min`(KOPIS 키가 없으면 `available=false`).
`GET /v1/places/{id}` 에 `since_year` · `licensed_as` · `marks[]` 추가. `GET /v1/directions/walk` 의 `legs[].coordinates`.
규칙 파일: `data/recommendation/{purpose_blend,multi_region,extra_roles,conditions}.json`, `data/signature/signature_rules.json`.


### 설계 점검 뒤에 더해진 것 (같은 날)
| 어디 | 필드 | 뜻 |
|---|---|---|
| `POST /courses/generate` 요청 | `replaces` | 여행 일정의 **하루**를 다시 짤 때 바꿀 그 날의 코스 id. 새 코스가 같은 여행의 같은 날이 되고(일차 · 여행 전체 예산을 물려받고, 다른 날이 가는 곳은 피한다) 옛 코스는 `status="replaced"` 로 탭에서 빠진다. 당일 코스의 id 면 무시한다. 남의 여행이면 403 |
| 코스 `warnings[]` | `EXTRA_UNAVAILABLE` | `extras` 로 부탁한 자리(술 한잔 · 야구 관람)를 코스에 넣지 못했다. `meta = {extra, label, vetoed}` — `vetoed=true` 면 함께 고른 목적 때문에 뺀 것(가족 → 술집). 문구는 `data/recommendation/extra_roles.json` 의 `missing` · `vetoed`. 여행은 어느 하루에라도 들어가면 말하지 않는다 |
| `POST /courses/{id}/save` | — | 여행 일정의 하루를 저장하면 **여행 전체**가 저장된다 (저장 안 된 날이 보존 기한에 지워지지 않게) |
| `GET /me/courses` 항목 | `day`, `days` | 여행 일정의 하루면 몇 일차 / 며칠짜리 |
| `POST /admin/places/{id}/photos` | multipart `file`, `make_cover` | 그 장소의 실제 사진(JPEG · PNG · WebP, 6MB 이하). 내용(매직 바이트)으로 형식을 확인하고 `/uploads/…` 로 서빙한다 |
