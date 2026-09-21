# 작업 진행 기록

> 세션이 끊겨도 이어서 작업할 수 있도록 남기는 체크포인트. 남은 일이 없어지면 이 파일은 삭제한다.

## 체크포인트 — 2026-09-21 06:50 KST

### 완료 · 검증됨
- 코드: `apps/api` · `apps/web` · `infra` · `.github` · 루트 설정 전부 작성됨 (이전 체크포인트의 "없음" 목록 해소. 마지막으로 `apps/api/{Dockerfile,.dockerignore,.env.example,README.md}` 추가)
- **api**: `ruff check` · `ruff format --check` · `mypy app` · `pytest -q`(192개) 전부 통과
  - 빈 SQLite에 `alembic upgrade head` 성공, `alembic check` 차이 없음
  - 그 DB로 `seed-config` → `ingest --provider file --all`(3지역 × 40곳) → uvicorn 기동 → `POST /v1/courses/generate` 실호출 200(코스 3개) · 예산 미달 422 `BUDGET_TOO_LOW` · `/readyz` 폴백 상태 확인
  - `.env.example`을 그대로 `.env`로 써서 부팅 확인 (빈 값 = 미설정)
- **web**: `npm run lint` · `tsc --noEmit` 통과. `next build`는 **OneDrive 밖 임시 복사본에서** 성공(18개 라우트). 목 모드 `next dev`로 `/` `/plan` `/course/demo` `/explore` `/admin` `/login` 200
- 문서: `docs/09`(구현/계획 구분) · `docs/15`(실제 트리) · 루트 `README.md` · compose/.env의 낡은 Alembic 주석 정리

### 남은 일
1. **목(MSW) ↔ 실제 API 계약 맞추기** — 화면은 목 기준으로 작성돼 실API와 필드가 어긋난 곳이 있었다(`/meta/purposes`, `GET /courses/{id}` 봉투). API를 계약으로 보고 `apps/web/src/lib/api/hooks.ts`에서 정규화. 실API로 아직 렌더링 검증 안 된 화면: `/chat` · `/my` · `/login` · `/admin/*`. **상태코드가 아니라 실제 렌더링으로 확인할 것** (200이어도 클라이언트 에러 바운더리가 뜰 수 있음).
2. `apps/web`에서 **제자리** `npm run build` 재확인 — dev 서버가 하나도 안 떠 있을 때. (이번에는 다른 세션의 dev 서버가 같은 `.next`를 쓰고 있어 확정 못 함)

### 이 환경에서 검증 불가 (도구·키 없음)
- Docker: `docker build`(api · web) · `docker compose up` — Dockerfile은 작성만 됨
- Terraform: `fmt` · `validate` · `tflint` · `checkov`
- PostgreSQL/PostGIS 경로(`ST_DWithin`, generated `geog` 컬럼) · Redis · OpenSearch(nori) · Celery 워커
- 외부 API: OAuth 3사 로그인 · LLM 3사 · kakao/naver/google/tourapi/data.go.kr 수집 · 길찾기 API — 어댑터의 정규화 로직은 단위 테스트로만 검증
- GitHub Actions 워크플로 실실행 · AWS 배포

### 의도된 미구현 (501)
- `GET /v1/admin/analytics/users` · `POST /v1/admin/uploads/presign` — 사유는 `apps/api/README.md`

### 환경 메모
- Windows 11, Node 22 / npm, Python 3.13, uv. **Docker · Terraform · pnpm 없음**
- 프로젝트가 OneDrive 경로 안 → `node_modules`/`.venv`를 포함한 재귀 탐색은 2분 넘게 걸림. 탐색 시 반드시 제외
- `apps/web/.next`는 **한 번에 한 프로세스만**. dev 서버가 떠 있는 동안 `.next` 삭제 · `next build` · 두 번째 dev 서버 금지. 시작 전에 3000/8000 포트 점유 프로세스부터 확인
- 메모리 부족 경고 이력 → 빌드·설치를 동시에 여러 개 돌리지 말 것
- PowerShell 5.1 `Invoke-RestMethod`는 한글 응답을 깨뜨려 보여 줌 → `curl.exe` 사용
