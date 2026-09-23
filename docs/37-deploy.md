# 37. 배포 — Render(API) + Vercel(웹)

> 2026-09-23. 창업자가 대시보드에서 따라 하는 순서. 설정 파일은 이미 저장소에 있다:
> `render.yaml`(API) · `apps/web/vercel.json`(웹) · `apps/api/.env.example` · `apps/web/.env.example`.
> 이 문서의 어떤 단계도 아직 실행되지 않았다.

## 0. 한눈에

```
브라우저 ──> https://naegajjanday.vercel.app          (Vercel, 서울 icn1)
               ├─ 화면(Next.js)
               └─ /v1/* · /uploads/*  ──프록시──> https://naegajjanday-api.onrender.com  (Render, 싱가포르)
                                                    └─ SQLite 파일 /var/data/naegajjanday.db (영구 디스크 5GB)
```

**왜 웹이 API 를 프록시하나.** 로그인 유지용 refresh 쿠키(`rt`)는 API 가 `SameSite=Lax` 로 심는다.
`vercel.app` 과 `onrender.com` 은 서로 다른 사이트라서, 웹이 Render 주소를 직접 부르면 브라우저가 이 쿠키를
보내지 않는다 → 로그인해도 새로고침하면 풀린다. `vercel.json` 의 rewrite 로 `/v1/*` 를 웹 도메인 아래에서
받으면 쿠키 · OAuth 콜백 · CORS 가 전부 "같은 사이트"가 되어 코드 수정 없이 해결된다.
(자체 도메인을 쓰면 `naegajjanday.com` + `api.naegajjanday.com` 처럼 같은 사이트로 묶는 방법도 있다 — §10.)

**왜 Postgres 가 아니라 SQLite 인가.** 전국 79만 곳 DB(약 1.2GB)는 지금 SQLite 파일 하나로 있고,
지금까지 실제로 검증된 경로도 SQLite 뿐이다. PostgreSQL/PostGIS 는 마이그레이션 · 코드는 있지만
실데이터로 돌려 본 적이 없다(`docs/PROGRESS.md` "검증 불가"). 첫 출시는 검증된 경로로 가고,
Postgres 는 §9 의 이전 절차로 따로 검증한다.

SQLite 의 대가:
- API 는 **인스턴스 1대** 고정(디스크는 한 인스턴스에만 붙는다). 수평 확장 불가.
- **무중단 배포 불가** — 배포할 때마다 수십 초 끊긴다.
- Render **무료 플랜에는 디스크가 없다** → 최소 Starter.
- rate limit · 캐시가 프로세스 메모리에 있다(재시작하면 초기화). Redis 는 없어도 동작한다.

## 1. 준비물 (창업자가 직접)

| 무엇 | 왜 | 비고 |
|---|---|---|
| GitHub 저장소 | Render · Vercel 모두 Git 에서 빌드한다 | **지금 이 저장소에는 원격(remote)이 없다.** 비공개 저장소를 만들어 push |
| Render 계정 + 결제 수단 | Starter 플랜 · 디스크는 유료 | |
| Vercel 계정 | 웹 | Hobby(무료)는 **비상업용**만 허용. 수익 서비스면 Pro |
| 카카오 개발자 콘솔 접근 | 지도 JS 키 도메인 · 카카오 로그인 Redirect URI | |
| (선택) 네이버 · 구글 OAuth 앱 | 소셜 로그인 | 없으면 로그인 버튼만 "준비 중" |
| SSH 키 | 전국 DB 파일을 Render 디스크로 올릴 때 | Windows 11 기본 `ssh-keygen` |

> 주의: `.github/workflows/deploy.yml` 은 main 에 push 하면 **AWS ECS 배포**를 시도한다. AWS 설정이 없으니
> 실패(빨간 X)로 끝난다. Render/Vercel 에는 영향 없음. 거슬리면 GitHub › Actions 에서 그 워크플로를 Disable.

## 2. Render — API 먼저

1. Render 대시보드 › **New › Blueprint** › GitHub 저장소 선택. 루트의 `render.yaml` 을 읽는다.
2. `sync: false` 값을 묻는다. 웹 주소를 아직 모르면 우선 예상 주소를 넣고 §4 에서 고친다.

   | 키 | 값 |
   |---|---|
   | `PUBLIC_BASE_URL` | `https://naegajjanday.vercel.app` (웹 주소 — OAuth 콜백이 웹 도메인을 거친다) |
   | `WEB_BASE_URL` | 위와 같은 값 |
   | `CORS_ORIGINS` | 위와 같은 값 (쉼표로 여러 개 가능, 끝에 `/` 없이) |
   | `KAKAO_CLIENT_ID` 등 | 있는 키만. 비우면 그 기능만 꺼진다 |

   `JWT_SECRET` · `WEBHOOK_SECRET` 은 Render 가 무작위로 만든다. 로컬 `.env` 값을 옮기지 말 것.
3. 첫 배포가 끝나면 `https://naegajjanday-api.onrender.com/readyz` 가
   `{"status":"ready", "components": {"database": {"status":"ok","backend":"sqlite"}, …}}` 를 돌려준다.
   이때 DB 는 **빈 테이블**이다(`db init` 이 만든 것). 데이터는 §6.
4. 서비스 주소가 `naegajjanday-api-xxxx.onrender.com` 처럼 접미사가 붙었으면 `apps/web/vercel.json` 의
   두 `destination` 을 그 주소로 고쳐 커밋한다.

설정 요약(`render.yaml`):
- 네이티브 Python 3.13 · `uv sync --frozen --no-dev` · 리전 싱가포르 · Starter(512MB).
- 시작: `python -m app.cli db init && uvicorn … --port $PORT --proxy-headers`. `db init` 은 SQLite 에서
  **새 테이블 · 컬럼만 추가**하고 데이터는 건드리지 않는다(Postgres 였다면 `alembic upgrade head`).
- 헬스 체크 `/readyz` (DB 연결까지 확인). `/healthz` 는 프로세스 생존만.
- 디스크 `/var/data` 5GB: DB 파일 · `uploads/`(운영자 사진) · `raw/`(서버에서 적재할 때 원본).
- Dockerfile 을 쓰지 않은 이유: 이미지가 non-root(uid 1001)로 돌아 Render 디스크 쓰기 권한과 어긋날 수 있다.
  Dockerfile 은 compose/AWS 용으로 그대로 둔다.

## 3. Vercel — 웹

1. Vercel › **Add New › Project** › 같은 GitHub 저장소.
2. 설정:

   | 항목 | 값 |
   |---|---|
   | Root Directory | `apps/web` |
   | Framework | Next.js (자동) |
   | Install / Build | `vercel.json` 이 지정: `npm ci` / `npm run build` |
   | Node.js Version | **22.x** (Settings › General. 로컬 · CI 와 같게) |
   | Function Region | `vercel.json` 이 `icn1`(서울) 지정 |

3. Environment Variables (Production):

   | 키 | 값 | 비고 |
   |---|---|---|
   | `NEXT_PUBLIC_API_URL` | `https://naegajjanday.vercel.app/v1` | **웹 자신의 주소 + /v1.** Render 주소를 직접 넣지 말 것 |
   | `NEXT_PUBLIC_SITE_URL` | `https://naegajjanday.vercel.app` | OG · sitemap · robots |
   | `NEXT_PUBLIC_KAKAO_MAP_KEY` | 카카오 **JavaScript 키** | 로컬 `apps/web/.env.local` 에 있는 그 키. 없으면 OSM 지도로 자동 전환 |
   | `NEXT_PUBLIC_API_MOCKING` | 넣지 않는다 | 켜면 가짜 데이터. 운영 금지 |
   | `NEXT_PUBLIC_GA4_ID` · `NEXT_PUBLIC_POSTHOG_KEY` · `NEXT_PUBLIC_MIXPANEL_TOKEN` | 선택 | 있는 것만 |

   `NEXT_PUBLIC_*` 는 **빌드할 때** 번들에 박힌다 → 값을 바꾸면 반드시 Redeploy.
4. Deploy. 주소가 `naegajjanday.vercel.app` 이 아니면(이름이 선점됨) §4 에서 Render 값을 맞춘다.

> **OG 이미지 글꼴 — 반영됨(2026-09-23).** `src/lib/og.tsx` 가 `node_modules/@sun-typeface/suit/…/*.otf` 를
> 실행 중에 읽는다. 첫 화면 OG(`/opengraph-image`)는 빌드 때 만들어져 문제없지만, 코스별 OG
> (`/course/[id]/opengraph-image`)는 요청 때 서버 함수에서 읽는다. Vercel 이 이 파일을 함수에 넣도록
> `apps/web/next.config.ts` 에 다음이 들어가 있다(첫 화면 OG 도 같이):
>
> ```ts
> outputFileTracingIncludes: {
>   "/course/[id]/opengraph-image": ["./node_modules/@sun-typeface/suit/fonts/static/otf/SUIT-{ExtraBold,Medium}.otf"],
> },
> ```
>
> 배포 뒤 §7 체크리스트의 "코스 OG 이미지"가 200 PNG 면 된 것이다.

**미리보기(Preview) 배포**: `NEXT_PUBLIC_API_URL` 을 Preview 환경에도 같은 값으로 넣으면 미리보기 화면이
운영 API 를 운영 도메인으로 부른다 → CORS 에 막힌다. 미리보기는 화면 확인용으로만 쓰고, Preview 환경 값은
`https://<그 미리보기 주소>/v1` 이 필요하다(주소가 매번 바뀌어 실용적이지 않음). 기존
`.github/workflows/preview.yml` 은 목(MSW) 모드 미리보기다.

## 4. 주소 맞추기 (웹 주소가 정해진 뒤)

Render › naegajjanday-api › Environment:
- `PUBLIC_BASE_URL` · `WEB_BASE_URL` · `CORS_ORIGINS` = 실제 웹 주소(끝 `/` 없이). Save → 자동 재시작.

Vercel: `NEXT_PUBLIC_API_URL` · `NEXT_PUBLIC_SITE_URL` 이 실제 주소인지 확인 → 바꿨으면 Redeploy.

## 5. 카카오 · 소셜 로그인 콘솔

카카오 개발자 콘솔 › 내 애플리케이션 › (앱):
1. **플랫폼 › Web › 사이트 도메인**에 `https://naegajjanday.vercel.app` 추가 (자체 도메인이 있으면 그것도).
   빠지면 지도 SDK 가 거부되고 화면은 OSM 지도로 떨어진다(무너지지는 않는다, docs/28 #14).
2. **카카오맵 사용 설정 ON** 확인 (JavaScript 키).
3. 카카오 로그인을 켤 때: **Redirect URI** = `https://naegajjanday.vercel.app/v1/auth/kakao/callback`
   (`PUBLIC_BASE_URL` + `/v1/auth/{provider}/callback`). 네이버 · 구글도 같은 모양:
   `…/v1/auth/naver/callback` · `…/v1/auth/google/callback`.

## 6. 전국 데이터를 운영 DB 로

**권장: 로컬의 전국 DB 파일을 그대로 올린다.** 로컬 `%LOCALAPPDATA%\naegajjanday\naegajjanday.db`
(2026-09-23 기준 약 1.2GB, 장소 79.5만 · 지역 · 축제 · TourAPI 사진 · 대학 캠퍼스 포함)는 그동안 평가
(`eval-courses`)와 화면 검증을 거친 바로 그 데이터다. 서버에서 적재를 다시 돌리면 같은 결과가 나온다는
보장이 없고 오래 걸린다. `apps/api/dev.db` 는 **가짜 샘플**이다 — 올리지 말 것.

1. **일관된 복사본 만들기** (로컬 dev 서버가 떠 있어도 안전 — WAL 까지 합친 한 파일이 나온다):
   ```powershell
   cd apps\api
   uv run python -c "import sqlite3,os; src=os.path.expandvars(r'%LOCALAPPDATA%\naegajjanday\naegajjanday.db'); dst=os.path.expandvars(r'%LOCALAPPDATA%\naegajjanday\deploy.db'); sqlite3.connect(src).execute(f\"VACUUM INTO '{dst}'\"); print(os.path.getsize(dst))"
   ```
2. **압축** (Windows 11 기본 tar):
   ```powershell
   cd $env:LOCALAPPDATA\naegajjanday
   tar -czf deploy.db.tgz deploy.db
   ```
3. **Render 에 SSH 키 등록**: Render › Account Settings › SSH Public Keys 에 `~\.ssh\id_ed25519.pub` 내용.
   서비스 › **Connect › SSH** 탭에 `srv-xxxx@ssh.singapore.render.com` 형태의 주소가 나온다.
4. **업로드** (`-s` 필수 — Render 는 SFTP 방식만 받는다). 집 인터넷 업로드 속도에 따라 수 분~수십 분:
   ```powershell
   scp -s deploy.db.tgz srv-xxxx@ssh.singapore.render.com:/var/data/
   ```
5. **교체** (서버 셸에서):
   ```bash
   ssh srv-xxxx@ssh.singapore.render.com
   cd /var/data && tar -xzf deploy.db.tgz && rm deploy.db.tgz
   mv naegajjanday.db naegajjanday.empty.db 2>/dev/null; rm -f naegajjanday.db-wal naegajjanday.db-shm
   mv deploy.db naegajjanday.db
   exit
   ```
   그리고 Render 대시보드 › **Manual Deploy › Restart service**. 재시작 때 `db init` 이 빠진 컬럼만 채운다.
6. **확인**: 서버 셸에서 `cd /opt/render/project/src/apps/api && .venv/bin/python -m app.cli ingest-bulk stats`
   → 장소 수가 로컬과 같은지. 확인 뒤 `/var/data/naegajjanday.empty.db` 는 지워도 된다.

**데이터 갱신**(나중에): 로컬에서 늘 하던 대로 `ingest-bulk …` → `eval-courses` 로 품질 확인 → 위 1~5 반복.
교체하는 동안(재시작 수십 초) 저장된 코스 · 계정은 **운영 DB 에만** 있으므로, 사용자가 생긴 뒤에는
통째 교체가 아니라 서버에서 직접 적재해야 한다: 원본을 `/var/data/raw/` 에 올리고
`NAEGAJJANDAY_DATA_DIR=/var/data` 가 이미 잡혀 있으니 서버 셸에서 `.venv/bin/python -m app.cli ingest-bulk …`.
그 전에 반드시 백업(아래 §8).

## 7. 스모크 테스트 체크리스트

사람 눈으로 (상태코드 200 이 아니라 화면을 읽는다):
- [ ] `https://naegajjanday-api.onrender.com/readyz` → `status: ready`, database `ok/sqlite`
- [ ] `https://naegajjanday.vercel.app/v1/meta/purposes` → JSON (프록시 동작)
- [ ] 첫 화면 → 계획 4단계 → 결과: 실제 상호 · "(업종 평균가)" 표기 · 합계가 예산 이하
- [ ] 결과 지도: 카카오맵이 뜨는가 (OSM 으로 떨어지면 §5 도메인 등록 누락)
- [ ] TourAPI 사진 카드에 "사진 ⓒ한국관광공사" 출처
- [ ] 화면 구석에 **MOCK 배지가 없다**
- [ ] 코스 공유 링크의 OG 이미지: `https://…/course/<id>/opengraph-image` 가 한글이 제대로 찍힌 PNG
- [ ] (로그인 키를 넣었다면) 카카오 로그인 → 코스 저장 → 새로고침 후에도 로그인 유지 → `/my`
- [ ] 휴대폰으로 한 번 (하단 탭 바)

자동 검사 — 기존 `npm run verify`(`e2e/site-cycle.mjs`)는 주소를 환경 변수로 받는다:
```powershell
cd apps\web
$env:E2E_WEB_URL = "https://naegajjanday.vercel.app"
$env:E2E_API_URL = "https://naegajjanday.vercel.app/v1"
npm run verify
```
- 코스를 실제로 여러 번 만든다 → 익명 생성 한도(`RL_GENERATE_ANON` 기본 10회/시간)에 걸릴 수 있다.
  검사하는 동안만 Render 에서 `RATE_LIMIT_ENABLED=false` → 끝나면 **반드시 true 로 되돌린다**.
- 계약서(`e2e/content-contract.json`)는 로컬 데이터로 기록된 것이다. 같은 DB 를 올렸다면 그대로 맞아야 한다.
- 운영 DB 에 검사용 코스가 남는다(저장 안 한 코스는 24시간 보관 대상 — 아래 참고).

## 8. 비용 · 무료 플랜의 함정 · 백업 · 되돌리기

비용 (2026-09 기준 대략, 가입 전에 각 가격 페이지 확인):
| 항목 | 월 |
|---|---|
| Render Starter 웹 서비스 (512MB) | 약 $7 |
| Render 디스크 5GB | 약 $1.25 ($0.25/GB) |
| Vercel Hobby | $0 — **비상업용만**. 광고 · 결제 등 수익이 있으면 Pro(약 $20/인) |
| 합계 | 약 $8~9 (Vercel Pro 면 +$20) |

무료로는 안 되는 이유:
- Render 무료 웹 서비스는 **디스크를 붙일 수 없다** → SQLite 파일이 재배포 때마다 사라진다.
- 무료는 15분 동안 요청이 없으면 **잠든다** → 다음 첫 요청이 30초 이상 걸린다(사용자는 "안 된다"로 느낀다).
- Render 무료 Postgres 는 1GB · **30일 뒤 만료** → 전국 DB 가 들어가지 않는다.

백업:
- Render 는 디스크를 **하루 한 번 자동 스냅숏**한다(대시보드 › Disks 에서 복원, 보관 기간은 Render 정책).
- 큰 작업(데이터 교체 · 서버 적재) 전에는 서버 셸에서 수동 백업:
  `sqlite3` 이 없을 수 있으니 `.venv/bin/python -c "import sqlite3; sqlite3.connect('/var/data/naegajjanday.db').execute(\"VACUUM INTO '/var/data/backup-YYYYMMDD.db'\")"`.
  디스크 5GB 에 DB 1.2GB → 백업은 2개까지만 두고 지운다.
- 올린 `deploy.db` 는 로컬에도 남겨 둔다(가장 쉬운 되돌리기 지점).

되돌리기:
- **API 코드**: Render › Events 에서 이전 배포 옆 **Rollback**. (디스크의 DB 는 되돌아가지 않는다)
- **웹**: Vercel › Deployments › 이전 배포 › **Instant Rollback**(또는 Promote to Production).
- **데이터**: 백업 파일을 `naegajjanday.db` 로 되돌려 놓고(§6-5 와 같은 방식) Restart service.
  또는 Render 디스크 스냅숏 복원.
- 스키마: SQLite 경로는 `create_all` 이 **추가만** 한다. 새 코드가 컬럼을 추가해도 옛 코드는 그 컬럼을 무시하므로
  코드 롤백만으로 동작한다.

정기 작업: 저장하지 않은 코스(24시간) · 탈퇴 계정(30일) 정리는 `purge-courses` · `purge-accounts` 명령이다.
Render Cron Job 은 이 디스크를 볼 수 없으므로(디스크는 한 서비스 전용), 당분간 서버 셸에서 주 1회 손으로
`.venv/bin/python -m app.cli purge-courses` · `purge-accounts` 를 돌린다. 사용자가 늘면 Postgres(§9)로 옮기고 Cron Job 으로.

## 9. 나중에: PostgreSQL 로 옮기기 (검증 전)

언제: API 를 2대 이상 띄워야 할 때, 무중단 배포가 필요할 때, 정기 작업을 Cron Job 으로 돌리고 싶을 때.
코드 쪽 준비는 되어 있다 — `render.yaml` 맨 아래 주석, Render 의 `postgresql://` 주소는
`app/core/config.py` 가 `postgresql+asyncpg://` 로 고쳐 읽고, 마이그레이션이 postgis · pg_trgm 확장을 만든다.
하지만 **실데이터로 돌려 본 적이 없다**. 순서:
1. Render Postgres(Basic-1gb 이상, 디스크 10GB+) 생성, 외부 접속 허용 목록에 내 IP 만.
2. 로컬에서 `DATABASE_URL=<External URL>` 로 `alembic upgrade head` → `seed-config` → 적재 명령 전체
   (`ingest-bulk all` → `tourapi` → `marks` → `universities --step load` → `regions` → `build-signatures` …,
   로컬에서 쌓아 온 순서 그대로). 원격 DB 로 79만 행을 넣는 것이라 **수 시간** 걸릴 수 있다.
3. `eval-courses --compare <SQLite 기준선>` 으로 SQLite 와 결과가 같은지 확인한 뒤에만 `DATABASE_URL` 을 바꾼다.
4. 계정 · 저장된 코스는 SQLite 운영 DB 에서 따로 옮겨야 한다(적재로는 안 생긴다).

## 10. (선택) 자체 도메인

도메인을 사면: Vercel 에 `naegajjanday.com`, 모든 주소 값(§4)을 그 도메인으로, 카카오 콘솔 도메인 · Redirect URI
추가. 프록시 구조는 그대로 둬도 된다. API 를 `api.naegajjanday.com` 으로 직접 노출하고 프록시를 빼는 것도
가능하다(같은 사이트라 `SameSite=Lax` 쿠키가 통한다) — 그때는 `NEXT_PUBLIC_API_URL=https://api.naegajjanday.com/v1`,
`PUBLIC_BASE_URL=https://api.naegajjanday.com`, `vercel.json` 의 rewrites 삭제.

## 알려진 한계 · 확인할 것

- Vercel 프록시(rewrite)를 거친 SSE 스트리밍(`/v1/courses/{id}/narrative`, `/v1/chat`)은 배포 뒤 실제로 확인해야 한다.
  끊기면 자체 도메인으로 API 를 직접 노출하는 §10 방식으로.
- `/metrics` 가 인증 없이 열려 있다(코스 수 · 평균 지연만). 민감 정보는 아니지만 알고 있을 것.
- rate limit 은 `X-Forwarded-For` 첫 값(= Vercel 이 넘긴 사용자 IP) 기준, 프로세스 메모리에 있다 → 재시작하면 초기화.
- 걷기 경로(`OSRM_FOOT_URL`)는 공개 FOSSGIS 서버(공정 사용)를 쓴다. 트래픽이 생기면 자체 OSRM 으로.
