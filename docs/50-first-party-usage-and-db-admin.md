# 50. 1자 사용량 통계 · 설정 · DB (2026-09-25)

> 계기: 창업자 — "날짜별로 어드민에서 사용량 통계, 그리고 DB 관리까지 하는 세팅창. 전체 사용자(비로그인 · 로그인) 모두 보이게."
> 관리자 "사용자 분석"은 PostHog · GA4 를 기다리며 501 이었다. 외부 도구 없이 우리 DB 로 센다.

## 무엇을 세나

| 지표 | 출처 |
|---|---|
| 방문자 · 로그인 · 비로그인 · 페이지 조회 | `visit` (새 테이블) — 웹이 페이지를 볼 때마다 `POST /v1/visits` |
| 신규 가입 | `user.created_at` |
| 로그인 횟수 | `refresh_token.created_at` (로그인 · 토큰 재발급 한 번 = 한 줄) |
| 코스 생성 · 비로그인 생성 | `recommendation_log` (저장 안 한 코스가 24시간 뒤 지워져도 남는다) |
| 저장 | `course.status ∈ saved · shared · completed` |
| 유입 경로 · 기기 | 기간 안의 첫 방문의 `referrer`(호스트만) · `device` |
| 주차별 재방문 | 처음 온 주 기준, N주 뒤에 다시 온 브라우저 비율 |

- **방문자 = 브라우저 수.** 같은 사람이 폰과 PC 로 오면 둘. 날짜는 한국 날짜.
- **개인정보:** 브라우저가 만든 임의 id(`localStorage › njd.visitor`)를 서버 비밀키로 HMAC 해 32자만 저장. IP · 전체 User-Agent 는 저장하지 않는다(기기 종류만). 봇 · 링크 미리보기 · 헤드리스 · `/admin` 은 세지 않는다. 1년 지난 기록은 API 시작 때마다 지운다(`visit_retention_days`). 개인정보처리방침에 적었다.
- 방문 기록은 **2026-09-25 배포부터** 쌓인다. 그 전 날짜의 방문자 0 은 "기록 없음"이다(화면이 그렇게 말한다).

## 화면

- `/admin/users` 사용자 분석: 기간 7 · 14 · 30 · 90일, 방문자(로그인 / 비로그인) · 페이지 조회 · 코스 생성 · 가입 계정 카드, 날짜별 막대 + **날짜별 표**, 유입 · 기기 · 로그인 수단, WAU/MAU, 주차별 재방문.
- `/admin/database` 설정 · DB: DB 크기 · 디스크 여유 · 테이블 행 수, **저장 안 한 코스 정리**(`cli purge-courses` 와 같은 일), **방문 기록 정리**(30일 미만은 거절, 미리 세고 확인), **백업**(SQLite backup API 로 디스크의 `backups/` 에, 최근 2개 유지, 디스크 여유가 DB 의 1.3배 미만이면 거절). 모든 쓰기는 `audit_log`.
- 저장한 코스 · 계정 · 장소는 이 화면에서 지우지 않는다.

## API

`POST /v1/visits` (공개, read 한도) · `GET /v1/admin/analytics/users?from&to` · `GET /v1/admin/database` · `POST /v1/admin/database/purge-courses?dry_run` · `POST /v1/admin/database/purge-visits` · `POST /v1/admin/database/backup` · `DELETE /v1/admin/database/backups/{name}`.
마이그레이션 `0011_visit` (PostgreSQL), SQLite 는 시작 때 `db init` 이 테이블을 만든다.

## 남은 것

- Render 디스크 5GB 에 DB 1.2GB — 백업 2개면 2.4GB. 디스크가 70%를 넘으면 백업을 하나만 남기거나 디스크를 늘린다.
- 백업은 같은 디스크 안이다: 디스크가 통째로 망가지면 같이 잃는다. 외부 보관(S3 등)은 저장소가 연결되면.
