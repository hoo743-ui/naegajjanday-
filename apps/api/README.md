# 내가짠데이 — api

예산 기반 코스 추천 서비스의 백엔드. FastAPI · SQLAlchemy 2 (async) · Pydantic v2 · Python 3.12+ · uv.

외부 의존성(PostgreSQL · Redis · OpenSearch · LLM · 지도 API)은 **전부 선택**이다. 아무 키도 없으면 SQLite + 메모리 캐시 + SQL LIKE 검색 + 직선거리(haversine) + 템플릿 문장으로 뜬다. 상태는 `GET /readyz` 의 `components` 로 확인한다.

## 빠른 시작 (Docker 없이)

```bash
cd apps/api
uv sync
cp .env.example .env                                  # 선택. 없어도 기본값으로 뜬다

uv run python -m app.cli db init                      # SQLite: 테이블 생성 / PostgreSQL: alembic upgrade head
uv run python -m app.cli seed-config                  # 지역 · 카테고리 · 태그 · 목적 · 템플릿 · 가중치
uv run python -m app.cli ingest --provider file --all # data/seed/places/*.json (3개 지역 × 40곳)
uv run uvicorn app.main:app --reload --port 8000
```

- 문서: <http://localhost:8000/v1/docs> · 스키마: `/v1/openapi.json`
- 헬스: `/healthz`(liveness) · `/readyz`(의존성별 상태) · `/metrics`

```bash
curl -s -X POST http://localhost:8000/v1/courses/generate -H 'content-type: application/json' -d '{
  "region": "seoul-hongdae", "purpose": "date", "party_size": 2,
  "budget_total": 40000, "start_at": "2026-09-26T18:00:00+09:00",
  "transport": "walk", "alternatives": 2
}'
```

예산이 최소 비용보다 낮으면 `422 BUDGET_TOO_LOW` (RFC 9457 problem+json, `meta.min_budget` 포함)를 준다.

> Windows PowerShell 5.1 의 `Invoke-RestMethod` 는 응답의 한글을 깨뜨려 보여 준다(클라이언트 디코딩 문제). `curl.exe` 나 `/v1/docs` 로 확인한다.

## 명령

| 명령 | 설명 |
|---|---|
| `uv run pytest -q` | 단위 + 통합 테스트 (임시 SQLite, 외부 호출 없음) |
| `uv run ruff check .` · `uv run ruff format --check .` | 린트 · 포맷 |
| `uv run mypy app` | 타입 검사 (`disallow_untyped_defs`) |
| `uv run alembic upgrade head` | 마이그레이션 (URL 은 항상 `DATABASE_URL` 에서 읽는다) |
| `uv run alembic check` | 모델과 마이그레이션의 차이 검출 |
| `uv run python -m app.cli create-admin --email me@example.com [--print-token]` | 관리자 권한 부여 (`--print-token`: 로컬용 15분 access token) |
| `uv run python -m app.cli ingest --provider kakao_local --region <slug>` | 공식 API 수집 (해당 키 필요) |
| `uv run python -m app.cli ingest-job <id>` | 관리자 API 로 만든 수집 작업을 Celery 없이 실행 |
| `uv run celery -A app.workers.celery_app worker --pool=solo` | 워커 (Windows 는 `--pool=solo`) |

## 전국 실데이터 적재

공공데이터포털의 **키가 필요 없는 공개 파일**만 쓴다(상가(상권)정보 · 착한가격업소 · 전국 표준데이터). 원본과 DB 는 저장소(OneDrive) 밖 `%LOCALAPPDATA%\naegajjanday\` 에 둔다. `apps/api/.env` 의 `DATABASE_URL` 이 그 DB 를 가리킨다(샘플 DB `dev.db` 는 그대로 남아 있다).

```powershell
cd apps/api
uv run python -m app.cli db init                      # 새 DB 스키마
uv run python -m app.cli seed-config                  # 카테고리·목적·템플릿 (샘플 장소는 넣지 않는다)
uv run python -m app.cli ingest-bulk download --source all   # raw\ 에 ~350 MB
uv run python -m app.cli ingest-bulk all              # semas → goodprice → 표준데이터 5종 (약 10분)
uv run python -m app.cli ingest-bulk stats            # 역할·시도별 건수, 추정/실측 가격, 지역 수
```

- 갱신: `download` 후 `ingest-bulk all` 을 다시 돌리면 변경분만 반영된다(멱등). 폐업 반영은 `ingest-bulk semas --close-unseen`.
- 일부만: `ingest-bulk semas --sido 서울 --sido 부산`, `ingest-bulk std --kind festivals`.
- 핫스팟을 추가·수정했다면(`data/bulk/regions_kr.json`) `ingest-bulk regions` — 지역을 다시 만들고 모든 장소를 가장 구체적인 지역으로 재배치한다(재적재 불필요).
- 자동 다운로드가 막히면(보안문자 등) 명령이 브라우저 절차를 출력한다. 받은 파일을 `--path` 로 넘기면 된다.
- 규칙은 전부 DATA: `data/bulk/regions_kr.json`(시도 slug·물가계수·핫스팟), `price_prior.json`(업종별 예상가), `bulk_rules.json`(제외 키워드·표준데이터 컬럼), `data/seed/categories.json` 의 `provider_mapping.semas`.
- 가격은 대부분 **예상**(`price_is_estimated=true`)이고 실측은 착한가격업소·박물관 관람료뿐이다. 영업시간·평점은 공개 데이터에 없다(평점 NULL, 영업시간 미상 = 상시로 취급).
- 서버를 띄운 채 적재했다면 **API 를 재시작**해야 지역 목록 캐시(1시간)가 갱신된다.

## 환경 변수

정본은 `app/core/config.py`, 예시는 `.env.example`. 값을 비워 두면 그 기능이 꺼지고 폴백으로 동작한다.

| 그룹 | 변수 | 비었을 때 |
|---|---|---|
| DB | `DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` |
| 캐시 · rate limit | `REDIS_URL` | 프로세스 메모리 |
| 검색 | `ES_URL` | SQL LIKE |
| LLM | `LLM_PROVIDER` + `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | 템플릿 문장 |
| 이동시간 | `TRAVEL_TIME_PROVIDER` + 키 | haversine × 이동수단 속도 |
| 로그인 | `KAKAO_*` · `NAVER_*` · `GOOGLE_*` | 해당 제공자 비활성 |
| 수집 | `KAKAO_REST_API_KEY` · `NAVER_SEARCH_*` · `GOOGLE_PLACES_API_KEY` · `TOURAPI_SERVICE_KEY` · `DATA_GO_KR_SERVICE_KEY` | `file` 제공자만 |

운영에서는 `JWT_SECRET`(32바이트 이상) · `COOKIE_SECURE=true` · `CORS_ORIGINS` 를 반드시 지정한다.

## 구조

```
app/
  main.py · cli.py
  api/v1/          라우터 (meta · courses · places · auth · me · chat · admin/*) — 얇게, 로직 없음
  schemas/         요청 · 응답 DTO (Pydantic)
  services/        유스케이스 (course · place · chat · narrative · auth · admin_* · ingestion_runner)
  repositories/    SQLAlchemy 쿼리 + interfaces.py(Protocol). geo.py = bbox + (PostgreSQL) ST_DWithin
  domain/          순수 파이썬, I/O 없음
    recommendation/  candidates → features(8종) → scorer → budget → composer → diversify → engine
    routing/         problem · held_karp(출발지 포함 ≤9 노드 정확해) · two_opt · ortools_solver(선택) · travel_time
  infra/
    db/            models · session · base
    ingestion/     PlaceProvider 어댑터(file · kakao_local · naver_search · google_places · tourapi · data_go_kr)
                   + pipeline(fetch → diff → upsert → dedupe/merge → stats → outbox)
    llm/           anthropic · openai · gemini + fallback 체인
    search/        OpenSearch client · index · outbox
    analytics/     ga4 · posthog · mixpanel
  prompts/         버전 붙은 YAML + loader
  core/            config · deps · errors(problem+json) · security · cache · rate_limit · sse · logging
  workers/         celery_app · tasks
alembic/           env.py(async) · versions/0001_initial.py
data/seed/         regions · categories · tags · purposes · places/*.json
tests/             unit/ · integration/
```

## 원칙

- **크롤링 금지.** 장소 데이터는 공식 Open API · 공공데이터 · 파일 업로드 · 사용자 제보로만 들어온다. 새 출처는 `infra/ingestion/providers/` 에 `PlaceProvider` 어댑터로 추가한다.
- **지역 · 목적 · 가중치는 데이터다.** 코드에 지역 이름이나 목적별 분기를 넣지 않는다. `tests/integration/test_new_region_by_data.py` 가 "시드 JSON 만으로 새 지역이 동작한다"를 검증한다.
- **도메인은 I/O 를 모른다.** `domain/` 은 DB · HTTP · 설정을 import 하지 않는다.

## 미구현 (501 `NOT_IMPLEMENTED`)

- `GET /v1/admin/analytics/users` — DAU/WAU · 리텐션 코호트. 클라이언트 이벤트 스트림(PostHog/GA4)이 있어야 하는 수치라, API DB 로 흉내 내지 않는다.
- `POST /v1/admin/uploads/presign` — S3 presigned URL. 객체 저장소 클라이언트(boto3 + 버킷 정책) 미연결. 그동안 배너는 외부 `image_url` 을 받는다.

## Docker

```bash
docker build -t njd-api apps/api
```

2-stage · `uv sync --frozen --no-dev` · UID 1001 `app` 사용자. api · worker · beat 가 같은 이미지를 쓰고 command 만 다르다(`docker-compose.yml`). 이미지는 마이그레이션을 하지 않는다 — compose 는 `API_MIGRATE_CMD`, 배포는 파이프라인이 먼저 돌린다.
