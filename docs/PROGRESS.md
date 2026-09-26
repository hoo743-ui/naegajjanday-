# 작업 진행 기록

> 세션이 끊겨도 이어서 작업할 수 있도록 남기는 체크포인트. 남은 일이 없어지면 이 파일은 삭제한다.

## 체크포인트 — 2026-09-26 11:00 KST (최신)

운영: 웹 https://naegajjanday.vercel.app (Vercel) · API https://naegajjanday-api.onrender.com (Render, SQLite /var/data). main 에 push = 배포. 마지막 커밋 `f1dc5d4`.

### 오늘 운영에 올라간 것 (2026-09-25 ~ 26)
| 영역 | 무엇 | 커밋 · 문서 |
|---|---|---|
| 추천 | 동네 "오는 이유"(핫플 55곳 먹거리 · 볼거리, `data/regions/draws.json`) 가중치 · 간판 잡음 제거 — 명물 포함 코스 50% → 85% | f05f928 |
| 추천 | 친구 모임 술자리 체인 78% → 0% (동네 술집 추정가 보정 + `ingest-bulk reprice`) | 1e90d3f |
| 추천 | 영화 한 편 옵션(티켓 크기 예산) · 영화관 603 · 공방 2,297 · 방탈출 231 · 보드게임 478 | e25c3ca · f8d2402 · docs/53 |
| 추천 | 관광지 실제 영업시간 501곳(TourAPI detailIntro2) — 밤 닫힌 곳 도착 58 → 0 | 03be6fc · docs/55 |
| 추천 | 처음 오는 사람 · 자주 오는 사람(`familiarity`, 로그인 기록 추론, 결과 화면 한 줄) | 3de7e50 |
| 추천 | 데이트 단체석 오판(고깃집 전체) · 밤 판정 · "상시운영" 가게 24시간 오독 수정 | 7fa516f · 83e23ef |
| 화면 | 결과 화면 "설정 바꾸기" · "오늘 지나갈 길"(실제 사진 띠) · "지도 크게"(전체 화면) · 골목 안 가볼 곳 | b52a83f · eae3cd8 · 7ec0b63 · feec5b4 · d23474c |
| 화면 | "꼭 들를 곳"을 지역 탭 → 코스 옵션(먼저 들르고 · 끝나고) | 1965acf |
| 데이터 | 대학 분캠퍼스 36곳 + 캠퍼스 이름 · 줄임말 검색(외대 · 성대 · 카이스트) | 86e4612 |
| 문구 | 동네 소개 55곳 · 브랜드 문구 재작성, 조사(을/를) 도우미 | 694e831 · docs/54 · feec5b4 |
| 운영 | **data sync**: 배포하면 seed · `data/bulk/delta/*.json` · 대학 · 가격 재계산이 서버 시작 때 자동 반영, 관리자 설정·DB 에 "데이터 반영" 카드 | f3589c1 · docs/57 |
| 운영 | CI 초록(SQLite pytest · 실제 API E2E · 390px 스크린샷 아티팩트 · 보안 스캔) | 6e51202 · docs/56 |
| 운영 | Vercel 이 "웹+문서 동시 push" 를 건너뛰던 문제 → `ignoreCommand` 를 마지막 성공 배포 기준으로 | f1dc5d4 |
| 품질 | 개념 점수표 `eval-concept`(23지표 + 처음/자주 짝 지표 3) — 지금 **전부 통과** | af202ec · docs/58 |

### 개선 파이프라인 (멈춰 둠)
- 점수표: `apps/api` 에서 `PYTHONIOENCODING=utf-8 uv run python -m app.cli eval-concept --sample quick --save <이름>` (약 4분, 공유 로컬 DB 읽기만). 고친 뒤 `--focus <지표> --compare <이름>` 이 **SHIP** 일 때만 배포. 기록: `%LOCALAPPDATA%/naegajjanday/eval/concept/`, 로그 `docs/58-concept-scorecard-log.md`.
- 대기열: `docs/59-improvement-backlog.md` — 창업자 요청을 맨 위에. 루프 한 회차 = 점수표 → 가장 나쁜 지표(모두 통과면 대기열 맨 위) → worktree 에이전트 → SHIP 이면 push → docs/59 에 한 줄.
- 세션 크론(3시간마다)은 **2026-09-26 11:00 에 꺼 둠**. 다시 켜려면 새 세션에서 같은 루프를 만들 것.
- 회차 결과: 1 데이트 단체석 24% → 0% · 2 밤 닫힌 곳 12.5% → 0% · 3 처음/자주(명물 비율 28%, 겹침 1.5%, 새 곳 63%).

### 남은 일 (다음에 이어서)
1. **대기열 2번 — 선택지가 늘어도 어지럽지 않게**: 위저드는 어디 · 누구와 · 얼마 · 언제만, 술 한잔 · 야구 · 영화 · 꼭 들를 곳 · 비는 결과 화면 "이것도 넣어 볼까요?" 칩 + 한 줄 말 입력. (docs/59)
2. 대기열 3~10번: 결과 화면 정리(돈 이야기 세 번), 친구 카페 저가 체인 44%, 혼자 밤 한 잔, 합쳐진 장소 이름, 꼭 들를 곳 경로 · 방향, 데이트 점심 다양성(고깃집 7/13), "상시운영" 해석기, 매일 영업시간 적재(Render 에서 `ingest-bulk tourapi-hours --limit 800`, 하루 1,000건 한도 공유 — 로컬에선 돌리지 말 것).
3. 자주 모드에서 긴 도보 3 · 닫힌 곳 1 — 점수표 지표가 아직 안 센다.
4. 화면 확인 못 한 것: 처음 모드의 "자주 오는 동네예요 → 다시 짜기" 줄, 꼭 들를 곳 옵션 블록(4단계) · 설정 바꾸기 시트의 꼭 들를 곳 칸.

### 작업 방식 메모
- 기능별로 worktree 에이전트를 병렬로(서로 다른 파일). worktree 에선 `UV_LINK_MODE=copy uv sync`, `apps/api/.env` 복사, node_modules 는 부모 것을 링크 후 커밋 전 제거. 로컬 `next build` · E2E 금지(메모리 16GB · OneDrive).
- 운영 화면 확인: 로컬 playwright(chrome channel)로 운영 URL 을 390px 로 찍는다. 익명 코스 생성은 시간당 10회 한도. 웹 배포 뒤엔 Vercel 상태가 READY 인지 확인.
- 공유 로컬 전국 DB `%LOCALAPPDATA%/naegajjanday/naegajjanday.db` 는 여러 작업이 읽는다 — 쓸 때는 CLI 로, 백업 후.

---

## 이전 체크포인트 — 2026-09-21 (대부분 해소됨)


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
