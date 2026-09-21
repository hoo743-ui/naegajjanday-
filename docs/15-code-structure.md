# 15. 코드 구조

> 모노레포. 앱은 `apps/`, 인프라는 `infra/`, 설계는 `docs/`. 각 앱은 독립적으로 빌드·배포된다.

## 1. 최상위

```
내가짠데이/
├─ index.html                 # 기존 랜딩(디자인 기준 — 컬러·타이포·짠이 원본)
├─ README.md
├─ docs/                      # 설계 문서 01~15
├─ apps/
│  ├─ api/                    # FastAPI + Celery (Python 3.12+, uv)
│  └─ web/                    # Next.js 15 (TypeScript, npm)
├─ infra/
│  ├─ docker/                 # 로컬용 이미지(Elasticsearch + nori 등)
│  └─ terraform/              # bootstrap/ + modules/ + envs/{shared,staging,prod}
├─ .github/
│  ├─ workflows/              # ci-api · ci-web · ci-infra · security · preview · deploy · _deploy-environment(재사용)
│  └─ CODEOWNERS · dependabot.yml · pull_request_template.md
├─ docker-compose.yml         # 기본: PostGIS · Redis · ES / --profile app: + api · worker · beat · web
├─ Makefile · scripts/dev.ps1 # 개발 명령 (Windows는 dev.ps1)
├─ scripts/ci/                # ecs-deploy.sh · smoke.sh (배포 워크플로가 호출)
├─ .env.example               # compose · Makefile · dev.ps1 용
└─ .pre-commit-config.yaml · .editorconfig · .gitattributes · .gitignore
```

## 2. Backend — `apps/api`

```
apps/api/
├─ pyproject.toml · uv.lock · Dockerfile · .dockerignore · .env.example · alembic.ini · README.md
├─ alembic/                          # env.py(async, URL은 DATABASE_URL에서)
│  └─ versions/                      # 0001_initial — ERD 전체, PostGIS는 postgresql에서만
├─ data/seed/                        # ★ 데이터 (코드 아님)
│  ├─ regions.json · categories.json · tags.json · purposes.json
│  └─ places/<region-slug>.json      # 샘플 장소 — file provider로 동일 파이프라인 통과
├─ app/
│  ├─ main.py                        # 앱 팩토리 · 미들웨어 · problem+json 예외 핸들러
│  ├─ cli.py                         # db init · seed-config · ingest · ingest-job · create-admin
│  ├─ core/                          # 횡단 관심사
│  │  ├─ config.py                   #   pydantic-settings
│  │  ├─ security.py                 #   JWT · refresh rotation · OAuth2 PKCE
│  │  ├─ rate_limit.py · cache.py    #   Redis 또는 인메모리 폴백
│  │  └─ errors.py · logging.py · deps.py · sse.py
│  ├─ api/v1/                        # ── Controller ──  HTTP ↔ DTO, 권한, rate limit
│  │  ├─ meta.py · courses.py · places.py · attractions.py
│  │  ├─ auth.py · me.py · chat.py · health.py
│  │  ├─ router.py · responses.py    #   v1 라우터 조립 · 공통 problem+json 응답 선언
│  │  └─ admin/                      #   places · events · banners · regions · scoring
│  │                                 #   templates · ingestion · analytics · system
│  ├─ schemas/                       # Pydantic DTO (요청/응답)
│  ├─ services/                      # ── Service ──  유스케이스 · 트랜잭션 · 캐시
│  ├─ repositories/                  # ── Repository ──  Protocol + SQLAlchemy 구현
│  ├─ domain/                        # ── Domain ──  순수 파이썬, 외부 import 금지
│  │  ├─ models.py                   #   PlaceCandidate · Slot · Template · ScoringProfile …
│  │  ├─ recommendation/
│  │  │  ├─ features.py              #   8개 피처 함수 (06 문서 3장)
│  │  │  ├─ scorer.py                #   가중합 + breakdown
│  │  │  ├─ budget.py                #   슬롯 예산 배분 · 선택 슬롯 제거 · 이월
│  │  │  ├─ candidates.py            #   하드 필터 (영업시간 · 가격 상한 · 제외)
│  │  │  ├─ composer.py              #   빔 서치 (W=40, K=12)
│  │  │  ├─ diversify.py             #   MMR 대안 코스
│  │  │  └─ engine.py                #   파이프라인 오케스트레이션
│  │  └─ routing/
│  │     ├─ travel_time.py           #   TravelTimeProvider · Haversine · 길찾기 API 어댑터
│  │     ├─ held_karp.py             #   정확해 DP (선행 제약 · 시간창)
│  │     ├─ ortools_solver.py        #   OR-Tools Routing (선택적 import)
│  │     ├─ two_opt.py               #   NN + 2-opt 폴백
│  │     └─ optimizer.py             #   솔버 선택 팩토리
│  ├─ infra/
│  │  ├─ db/                         #   세션 · ORM 모델 (ERD 1:1)
│  │  ├─ llm/                        #   LLMProvider Protocol · anthropic/openai/gemini · 폴백
│  │  ├─ search/                     #   ES 클라이언트 · nori 매핑 · outbox 동기화
│  │  ├─ ingestion/
│  │  │  ├─ base.py · pipeline.py · dedupe.py · price.py · stats.py
│  │  │  ├─ registry.py · config_loader.py   # provider 이름 → 어댑터 · 시드 JSON upsert
│  │  │  └─ providers/               #   kakao_local · naver_search · google_places
│  │  │                              #   tourapi · data_go_kr · file_provider
│  │  └─ analytics/                  #   GA4 MP · PostHog · Mixpanel 서버 이벤트
│  ├─ prompts/                       # ★ Prompt Layer — 코드와 분리된 버전 자산
│  │  ├─ course_narrative.v1.yaml · course_narrative_stream.v1.yaml · narrative_fallback.v1.yaml
│  │  ├─ review_sentiment.v1.yaml · chat_system.v1.yaml · tag_extraction.v1.yaml
│  │  └─ loader.py
│  └─ workers/                       # Celery 앱 · 태스크 · 스케줄
└─ tests/                            # conftest.py · factories.py
   ├─ unit/                          # 도메인 — DB 불필요, 수 초
   └─ integration/                   # SQLite + httpx AsyncClient, 시드 → API 호출
```

### 의존 방향

```
api/v1 ──▶ services ──▶ domain
               │           ▲ (Protocol)
               ▼           │
         repositories ──▶ infra
```

- `domain`은 `fastapi`, `sqlalchemy`, `httpx`를 import하지 않는다. Repository·TravelTimeProvider·LLMProvider는 **Protocol**로만 안다.
- 새 데이터 출처 = `infra/ingestion/providers/`에 파일 1개. 새 피처 = `features.py` 함수 1개 + `scoring_profile.weights` 키. 새 LLM = `infra/llm/`에 파일 1개.

## 3. Frontend — `apps/web`

```
apps/web/
├─ package.json · next.config.ts · tsconfig.json · components.json · Dockerfile · .env.example · README.md
├─ public/lottie/                    # Lottie JSON  (+ mockServiceWorker.js — 개발 전용, 운영 이미지에서 제거)
└─ src/
   ├─ app/
   │  ├─ layout.tsx · providers.tsx · globals.css   # 디자인 토큰(@theme) — index.html과 동일
   │  ├─ (marketing)/page.tsx        # 랜딩 — Hero 3막 시퀀스
   │  ├─ plan/                       # 4단계 위저드
   │  ├─ course/[id]/                # 결과 (지도 + 타임라인 + 스코어 분해)
   │  ├─ explore/ · chat/ · my/ · login/
   │  ├─ admin/                      # 대시보드 · 승인 · 관광지 · 이벤트 · 배너 · 지역 · 추천설정 · 분석
   │  └─ loading.tsx · error.tsx · global-error.tsx · not-found.tsx   # 전부 짠이
   ├─ components/
   │  ├─ mascot/                     # Jjani(mood 6종, 파츠별 애니메이션) · Bubble · Loader · EmptyState
   │  ├─ landing/ · plan/ · course/ · explore/ · chat/ · my/ · login/ · admin/ · layout/
   │  ├─ LottiePlayer.tsx            # lottie 런타임을 필요할 때만 동적 로드
   │  └─ ui/                         # shadcn/ui
   ├─ lib/
   │  ├─ api/                        # client(problem+json → ApiError.code) · types · hooks · admin · sse · mock-ready
   │  ├─ analytics/                  # track() → GA4 · PostHog · Mixpanel 어댑터, 타입드 이벤트 카탈로그
   │  ├─ auth/                       # access 메모리 보관 · refresh 쿠키
   │  └─ format.ts · utils.ts · mascot-copy.ts   # 에러 code → 짠이 mood + 문구
   ├─ mocks/                         # MSW — NEXT_PUBLIC_API_MOCKING=enabled 일 때만
   ├─ instrumentation.ts             # 목 모드에서 서버 측 msw/node 기동
   └─ middleware.ts                  # /my · /admin 보호
```

원칙
- 컴포넌트에 장소·지역·목적 리터럴 없음. 전부 `/v1/meta/*` 응답으로 렌더한다. (랜딩 Hero의 연출용 수치만 예외)
- API 불가 시 가짜 데이터로 조용히 대체하지 않는다 — 짠이 에러 상태 + 재시도.
- GSAP은 랜딩(`HeroSequence`)에서만 import한다. Lottie 런타임은 `LottiePlayer`가 필요할 때 동적 로드한다.
- `hooks.ts`가 API 응답을 화면 타입으로 정규화하는 유일한 지점이다. 목(MSW)과 실제 API가 어긋나면 **API를 계약으로 보고** 여기서 맞춘다.

## 4. Infra — `infra/terraform`

```
infra/terraform/
├─ bootstrap/   # tfstate용 S3 버킷 · 잠금 (최초 1회, 로컬 state)
├─ modules/     network · alb · ecs_service · rds · elasticache · opensearch
│               edge(CloudFront·WAF·Route53·S3) · observability · cicd_oidc · ecr · scheduled_tasks
│               stack(위 모듈을 환경 하나로 조립 — staging/prod가 공유)
└─ envs/
   ├─ shared/   # 계정 공통: ECR · GitHub OIDC 역할
   ├─ staging/  # 최소 사양 · 단일 NAT · 야간 중지
   └─ prod/     # Multi-AZ · 오토스케일 · 삭제 보호
```

## 5. 로컬 실행 (Docker 없이)

```powershell
# API
cd apps/api
uv sync
uv run python -m app.cli db init
uv run python -m app.cli seed-config
uv run python -m app.cli ingest --provider file --all
uv run uvicorn app.main:app --reload --port 8000      # http://localhost:8000/v1/docs

# Web (다른 터미널)
cd apps/web
npm install
npm run dev                                            # http://localhost:3000
```

Docker가 있다면 루트에서 `docker compose up -d`로 PostGIS·Redis·Elasticsearch를, `docker compose --profile app up -d --build`로 api·worker·beat·web까지 띄운다 (`infra/docker/README.md`).

> **Windows + OneDrive 주의** — 저장소가 OneDrive 동기화 폴더 안에 있으면 `apps/web/.next`의 파일이 깨져(`EINVAL: readlink`, 매니페스트 누락 → 전 페이지 500) 보일 수 있다. dev 서버를 끄고 `.next`를 지운 뒤 다시 시작하면 복구된다. 같은 `apps/web`에서 `next dev`와 `next build`(또는 dev 서버 두 개)를 **동시에** 돌려도 같은 증상이 난다 — `.next`를 공유하기 때문이다. 근본 해결은 저장소를 OneDrive 밖(예: `C:\dev\`)으로 옮기는 것.

## 6. 네이밍 · 컨벤션

| 대상 | 규칙 |
|---|---|
| Python | `snake_case`, 모듈은 명사, 서비스 메서드는 동사(`generate_course`) |
| TS | 컴포넌트 `PascalCase.tsx`, 훅 `useX`, 유틸 `camelCase` |
| DB | 테이블 단수형 `snake_case`, FK `<table>_id`, 시각 `*_at`, 날짜 `*_on` |
| API | 복수 명사 리소스, 동작은 하위 경로(`/courses/{id}/swap`) |
| 에러 코드 | `UPPER_SNAKE` — 프론트 `mascot-copy.ts`와 1:1 |
| 이벤트 | `object_verb` 과거형(`course_saved`) |
| 커밋 | Conventional Commits |
| 프롬프트 | `<name>.v<N>.yaml`, 변경 시 버전 증가(기존 파일 수정 금지) |
