# 47. 알림 종 · 외부 API 한도 알림

> 2026-09-24 창업자: "한계가 정해진 API KEY 는 알림이 필요" · "로컬 시간 기준으로 축제 · 이벤트를 알려 주는 알림창 — 격자 · 디자인 체계는 건드리지 말고 오른쪽 위에".

## 1. 알림 종 (`components/layout/NotificationBell.tsx`)
- 헤더 오른쪽(로그인 앞)에 종 하나. 격자 · 탭바 · 색 체계는 그대로(드롭다운은 기존 `DropdownMenu`, 점은 토마토 = 선택/알림).
- **축제 · 행사 — 보는 사람의 기기 시각 기준**: 오늘부터 7일(`/events?from&to`, 기기 날짜로 계산). 오늘 시작 → 오늘 마감 → 내일 시작 → 이번 주말 → 진행 중 순, 6개까지. 마지막으로 본 코스의 동네(`jj-last-area`, 결과 화면이 첫 장소 주소의 시 · 구를 저장)가 있으면 그 동네 것이 먼저(4개까지, 나머지는 전국).
- 누르면 둘러보기의 축제로(`/explore?type=festival&q=이름`).
- 읽음은 이 기기에만(`jj-notif-seen`). 종을 열면 모두 읽음. 저장이 막혀 있어도 알림은 보인다.
- 날짜를 읽기 전에는 행사를 부르지 않는다(날짜 없이 부르면 전국 행사 전부가 온다).

## 2. 외부 API 한도 (`infra/api_usage.py`, `data/quotas.json`, `GET /v1/admin/quotas`)
- 프로세스마다 한 번(API 시작 · CLI) httpx 응답 훅을 건다 → 어디서 부르든(둘러보기 링크 · 블로그 수 · 길찾기 · 대량 적재) 호스트로 API 를 알아내 `api_usage(provider, day)` 를 1 올린다. 세다가 실패해도 요청은 그대로(로그 한 번).
- "다 썼다"는 신호: HTTP 429, 공공데이터포털은 200 + 본문의 `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR`(코드 22).
- 응답 헤더에 한도가 오면(`x-ratelimit-limit/remaining`) 그 값이 우리 셈보다 우선. **TourAPI 는 헤더로 하루 1,000회임을 2026-09-24 확인**(개발계정). 둘러보기 상세의 공식 홈페이지 조회가 곳당 1회 쓰므로(일주일 캐시) 운영 전 운영계정 전환이 필요하다.
- 한도 표(`data/quotas.json`)는 출처를 같이 적는다. 모르는 한도는 null(셈만), 확인 못 한 기본값은 `verified: false`.
- 상태: 80% warn · 95% critical · 소진 exhausted. 관리자 · 운영자의 종에 뜬다(10분마다 다시 읽음).
- 터미널: `uv run python -m app.cli api-usage` (SQLite 에 표가 없으면 만든다). PostgreSQL 은 alembic 0010.

## 3. 한도 가드 — 넘기 전에 멈춘다 (`infra/quota_guard.py`, 창업자 2026-09-26)
> "API 한도를 넘을 위험이 보이면 알아서 멈추고 대안을 생각해라."

위 훅은 호출한 **뒤에** 센다. 대량 작업은 이제 배치마다 **먼저** 묻는다: "이번 배치를 쓰면 남는 것이 `한도 − reserve` 아래로 가나?"
(`reserve` = 사이트가 그날 쓸 몫, `quotas.json › <provider>.reserve` — TourAPI 100 · 공공데이터 50 · 카카오 로컬 1,000 · 네이버 검색 500).

- 넘으면 쓰기 도중이 아니라 배치 사이에서 멈추고, 로그 `quota.stop provider=… remaining=… reserve=… job=… cursor=…`,
  멈춘 자리를 `ingestion_job`(job_type `quota`, status `deferred`, `cursor` = 다음에 이어 갈 곳 · 남은 수 · `resume_after` 다음 날 00:05 KST)에 적는다.
- 그리고 **대신한다**(순서대로): ① 디스크의 파일(소상공인 · 인허가 원파일, `raw/tourapi` 에 캐시된 페이지, `data/bulk/delta` 의 답 — `--from-file`)
  ② 이미 저장된 답(업종 기본 영업시간, 지난번 캠퍼스 좌표) ③ 나머지는 다음 날 일정(매일 04:30 영업시간 작업이 큐 순서대로 이어 간다).
- 걸려 있는 곳: TourAPI 영업시간(`tourapi_hours.run`, 호출마다 · 헤더의 남은 수를 믿는다), TourAPI 전국 목록(`tourapi_bulk.download` — 동기 `httpx.Client` 라
  훅이 못 세는 곳, 페이지마다 가드가 센다 · 멈추면 지난주 캐시 페이지를 지우지 않고 쓴다), 대학 캠퍼스 카카오 좌표(`universities.build` — 지난번 좌표를 먼저,
  카카오는 없을 때만), 지역별 공급자 적재(`IngestionPipeline.run` — 시작 전에 한 지역 몫 60회를 묻고, 모자라면 cursor 를 둔 채 deferred).
- 한도를 모르는 공급자(`limit: null`)는 막지 않고 센다.
- 구경하는 가게(docs/63)는 외부 호출 0회다(소상공인 원파일에서 만든 델타).

## 남은 것
- 관리자에게 이메일 · 슬랙으로 보내기(지금은 화면 종뿐).
- 네이버 클라우드 지도 · 카카오 로컬의 실제 한도를 콘솔에서 확인해 `quotas.json` 에 넣기.
