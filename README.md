# 내가짠데이

> "내 예산에 맞게, 내가 짠 데이."
> 지역·예산·인원·목적을 넣으면 **예산 안에서 가장 효율적인 하루 코스와 동선**을 계산해 주는 AI 코스 최적화 플랫폼.

맛집 하나를 추천하는 서비스가 아니다. 식사 → 카페 → 관광지 → 술집으로 이어지는 **코스 전체**를, 총액과 총 이동시간을 보장하면서 짠다.

## 구성

| 경로 | 내용 |
|---|---|
| [`docs/`](docs) | 설계 문서 15종 |
| [`apps/api`](apps/api) | FastAPI · 추천 엔진 · 경로 최적화 · 수집 파이프라인 · LLM 레이어 |
| [`apps/web`](apps/web) | Next.js 15 · 랜딩 · 코스 위저드 · 결과 · 챗봇 · 관리자 |
| [`infra/`](infra) | Terraform(AWS) · 로컬 Docker |
| [`.github/workflows`](.github/workflows) | CI · 보안 스캔 · 배포 |
| `index.html` | 기존 랜딩 페이지 — 디자인 토큰과 마스코트 **짠이**의 원본 |

## 설계 문서

| # | 문서 | # | 문서 |
|---|---|---|---|
| 01 | [서비스 구조도](docs/01-service-architecture.md) | 09 | [CI/CD](docs/09-cicd.md) |
| 02 | [DB ERD](docs/02-erd.md) | 10 | [AWS 인프라](docs/10-aws-infrastructure.md) |
| 03 | [API 명세](docs/03-api-spec.md) | 11 | [운영비 예상](docs/11-operating-cost.md) |
| 04 | [화면 설계](docs/04-screen-design.md) | 12 | [유지보수 전략](docs/12-maintenance-strategy.md) |
| 05 | [UX 플로우](docs/05-ux-flow.md) | 13 | [확장성 전략](docs/13-scalability-strategy.md) |
| 06 | [추천 알고리즘 · 경로 최적화](docs/06-recommendation-algorithm.md) | 14 | [MSA 전환 전략](docs/14-msa-migration.md) |
| 07 | [데이터 수집 구조](docs/07-data-pipeline.md) | 15 | [코드 구조](docs/15-code-structure.md) |
| 08 | [서버 아키텍처 · 보안](docs/08-server-architecture.md) | | |

## 핵심 설계 결정

1. **지역·목적·코스 템플릿·스코어링 가중치는 전부 DB 데이터다.** 새 지역은 관리자 화면에서 row를 추가하고 수집을 돌리면 열린다. 코드 배포 0회. CI에 이를 검증하는 테스트가 상주한다.
2. **LLM은 점수를 매기지 않는다.** 선택은 결정적 알고리즘(8개 피처 가중합 → 빔 서치 → TSP)이 하고, LLM은 리뷰 감성 배치·결과 설명·챗봇 입력 해석만 맡는다. 결과가 재현 가능하고, LLM이 죽어도 추천은 동작한다.
3. **Claude · OpenAI · Gemini 호환.** `LLMProvider` 프로토콜 + 코드와 분리된 Prompt Layer(`app/prompts/*.yaml`).
4. **수집은 공식 Open API와 공공데이터만.** 지도 서비스 웹 화면 크롤링은 약관·법적 리스크 때문에 하지 않는다 ([07](docs/07-data-pipeline.md)).
5. **모든 외부 의존에 폴백이 있다.** Redis·검색엔진·길찾기 API·LLM 어느 것이 죽어도 코스 생성은 된다. 그래서 로컬에서 Docker 없이 SQLite만으로도 돈다.
6. **모듈러 모놀리스.** 경계는 MSA 후보 단위로 나눠 두되, 분리는 트리거가 생겼을 때만 ([14](docs/14-msa-migration.md)).

## 빠른 시작 (Windows · Docker 불필요)

```powershell
# 1) API — http://localhost:8000/v1/docs
cd apps/api
uv sync
uv run python -m app.cli db init
uv run python -m app.cli seed-config
uv run python -m app.cli ingest --provider file --all
uv run uvicorn app.main:app --reload --port 8000

# 2) Web — http://localhost:3000  (새 터미널)
cd apps/web
npm install
npm run dev
```

`apps/api/data/seed/`의 장소는 **가상의 샘플 데이터**다. 실제 데이터는 각 provider API 키를 `.env`에 넣고 `ingest --provider kakao_local --region <slug>`로 수집한다.

검증: `cd apps/api; uv run ruff check .; uv run mypy app; uv run pytest -q` · `cd apps/web; npm run lint; npm run typecheck; npm run build`
앱별 상세는 [`apps/api/README.md`](apps/api/README.md) · [`apps/web/README.md`](apps/web/README.md), Docker 스택은 [`infra/docker/README.md`](infra/docker/README.md).

> **Windows + OneDrive 주의** — 이 폴더가 OneDrive 동기화 경로 안에 있으면 `apps/web/.next`가 깨져(`EINVAL: readlink`, 매니페스트 누락 → 전 페이지 500) 보일 수 있다. dev 서버를 끄고 `.next`를 지운 뒤 재시작하면 복구된다. `next dev`와 `next build`를 같은 폴더에서 동시에 돌리지 않는다(`.next` 공유). 근본 해결은 저장소를 OneDrive 밖으로 옮기는 것.

## 마스코트 — 짠이

머리에 지도 핀을 꽂은 금화. "짠!"(완성) · "짠돌이"(알뜰) · "내가 짠 데이"(코스를 짜다). 랜딩·로딩·결과·챗봇·빈 화면·에러 화면 전부에 표정을 바꿔 가며 등장한다 ([04](docs/04-screen-design.md)).
