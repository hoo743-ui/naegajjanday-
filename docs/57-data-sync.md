# 57. 데이터 반영 자동화 (data sync)

코드와 함께 배포되는 데이터 파일이 운영 DB 에 **저절로** 들어가게 한다. 전에는 배포 뒤 Render Shell 에서 명령 세 개를
기억해 돌려야 했고, 하나라도 잊으면 웹에는 기능이 보이는데 데이터가 없었다(예: "영화 한 편" 은 `activity.cinema`
카테고리와 영화관 추가분이 있어야 한다).

## 무엇을 반영하나

순서대로, 파일 내용의 sha256 이 지난번에 반영한 것과 다를 때만:

| 항목 (key) | 파일 | 하는 일 (예전 명령) |
|---|---|---|
| `seed` | `data/seed/{categories,tags,regions,purposes}.json` | `seed-config` |
| `delta/<이름>.json` | `data/bulk/delta/*.json` (이름순, 새 파일도 자동으로) | `places` 가 있으면 `ingest-bulk delta <파일>`, `intros` 가 있으면(영업시간 답, docs/55) `ingest-bulk tourapi-hours --from-file <파일>` |
| `anchors/universities.json` | `data/anchors/universities.json` | `ingest-bulk universities --step load` |
| `prices/price_prior.json` | `data/bulk/price_prior.json` · `regions_kr.json` | `ingest-bulk reprice` |
| `rules/hours_text` | `app/infra/ingestion/hours_text.py` (코드) | `ingest-bulk tourapi-hours --reapply` — 영업시간 해석기가 바뀌면 저장된 TourAPI 답을 다시 읽는다(호출 0건) |

`rules/*` 는 파일이 아니라 **코드의 규칙**이다: 모듈 파일의 해시가 바뀌면(= 규칙을 고친 배포) 이미 저장된 행을 새 규칙으로 다시 만든다.
외부 호출은 하지 않는다. 목록은 `app/services/data_sync.py::RULES`.

- 무엇을 반영했는지는 같은 DB 의 `data_sync` 테이블(= 영구 디스크)에 파일별 해시 · 시각 · 한 줄 결과 · 마지막 오류로 남는다.
  `@run` 행은 마지막 전체 실행 시각.
- 반영에 성공한 항목만 기록한다. 실패한 항목은 오류를 남기고 다음 실행 때 다시 시도하며, 한 파일이 실패해도 다음 파일은 돈다.
- 로더는 원래부터 멱등이다(코드 · 외부 id 기준 upsert, 바뀌지 않은 행은 건너뜀). 그래서 두 번 돌려도, 빈 DB 여도,
  중간에 끊겨도(끊긴 항목은 기록되지 않아 다음에 다시) 안전하다. 이미 손으로 반영해 둔 운영 DB 에 처음 돌면 모든 항목이
  "반영"으로 찍히지만 실제로는 `unchanged` 로 지나간다.
- 쓰기는 `BulkWriter.BATCH_SIZE`(2000행)마다 커밋 → SQLite 쓰기 잠금을 오래 잡지 않는다. 항목 사이에 이벤트 루프를 양보한다.

## 언제 도나 — Render

- **preDeployCommand 는 못 쓴다.** Render 의 build · pre-deploy 는 별도 머신에서 돌고 영구 디스크가 붙지 않는다
  (플랜과 무관, [Render Docs › Persistent Disks](https://render.com/docs/disks), [Deploys](https://render.com/docs/deploys)).
- 그래서 **앱이 켜진 뒤 백그라운드 작업**으로 돈다(`app/main.py` lifespan → `data_sync.run_on_start`). 5초 기다린 뒤
  시작하므로 `/readyz` 헬스 체크와 요청은 바로 받는다. 끝나면 로그에 `data_sync.done applied=… skipped=… failed=…`.
- 한 프로세스만 돌도록 DB 파일 옆 `naegajjanday.db.data-sync.lock` 에 OS 파일 잠금(flock)을 건다. 프로세스가 죽으면
  잠금도 풀린다(남은 잠금 파일은 무해).
- 켜짐 조건: `DATA_SYNC_ON_START` 가 없으면 **production(APP_ENV=production)에서만** 돈다. 로컬 전국 DB 는 기본으로 건드리지
  않는다. 끄려면 `DATA_SYNC_ON_START=false`, 로컬에서 켜려면 `true`. 시작 지연은 `DATA_SYNC_DELAY_S`.
- 걸리는 시간: 전국 DB 사본(1.2 GB)에서 여섯 항목 전부 약 15초(설정 3.8s, 장소 추가분 셋 4s, 영업시간 답 6.4s, 캠퍼스 0.5s —
  사본에는 이미 들어 있던 데이터라 대부분 `unchanged`). 처음 들어가는 행(추가분 약 5천 곳, 영업시간 780건)이 있어도 1분 안쪽.
  아무것도 안 바뀐 배포는 해시만 비교하고 끝.

## 관리자 화면

설정 · DB (`/admin/database`) 오른쪽 맨 위 **데이터 반영** 카드: 마지막 반영 시각, 파일마다 완료 / 대기 / 실패(오류 문구),
**지금 반영하기** 버튼(배포 때와 같은 작업, 이미 반영된 파일은 건너뜀, 감사 기록 `sync data`). 도는 동안 3초마다 새로 본다.

API: `GET /v1/admin/database/data-sync`, `POST /v1/admin/database/data-sync` (202, 이미 돌고 있으면 409).

## 손으로 돌릴 때

```bash
.venv/bin/python -m app.cli data-sync --status   # 무엇이 반영됐나
.venv/bin/python -m app.cli data-sync            # 바뀐 것만 반영
.venv/bin/python -m app.cli data-sync --force    # 전부 다시 (멱등이라 안전)
```

## 창업자가 손으로 할 일

- **없음.** 다음 배포부터 자동이다. Render 설정을 바꿀 필요도 없다(`APP_ENV=production` 이 이미 있다).
- 새 데이터 파일을 추가할 때는 `data/bulk/delta/` 에 넣고 커밋만 하면 된다. 새 카테고리가 필요하면 같은 커밋에
  `data/seed/categories.json` 도 — seed 가 먼저 반영된다.
- 이 목록에 없는 것은 여전히 손으로: 원본이 필요한 전국 적재(`ingest-bulk semas|all|tourapi …`), `ingest-bulk marks`,
  그리고 하루 한도 안에서 TourAPI 를 부르는 `ingest-bulk tourapi-hours`(파일이 아니라 호출이라 자동 반영 대상이 아니다, docs/55).
  docs/55 의 "Render Shell 에서 `--from-file`" 단계는 이제 필요 없다.

## 코드

`app/services/data_sync.py` (계획 · 잠금 · 반영 · 상태), `app/infra/db/models/ops.py::DataSync`,
`alembic/versions/0013_data_sync.py`, `app/api/v1/admin/database.py`, `app/cli.py data-sync`,
웹 `apps/web/src/app/admin/database/page.tsx`, 테스트 `tests/integration/test_data_sync.py`.
