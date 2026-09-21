# 12. 유지보수 전략

> 이 서비스에서 유지보수의 핵심 명제: **"새 지역이 추가되어도 코드 수정 없이 데이터만 추가하면 동작한다."**

## 1. 무엇이 데이터이고 무엇이 코드인가

| 바뀌는 것 | 어디에 있나 | 바꾸는 사람 | 배포 필요 |
|---|---|---|---|
| 지역 (신규 오픈·반경·키워드) | `region` 테이블 | 운영자 (Admin › 지역) | ❌ |
| 카테고리, 출처별 카테고리 매핑 | `category.provider_mapping` | 운영자 | ❌ |
| 목적 (데이트·여행·… 신규 `회식`) | `purpose` | 운영자 | ❌ |
| 코스 구성·순서·예산 비율·시간창 | `course_template`, `template_slot` | 운영자 | ❌ |
| 스코어링 가중치·파라미터 | `scoring_profile` (버전 관리) | PM/데이터 | ❌ |
| 목적별 태그 선호 | `purpose_tag_affinity` | 운영자 | ❌ |
| 장소·이벤트·배너 | 각 테이블 | 운영자 / 수집 배치 | ❌ |
| 프롬프트 문구 | `app/prompts/*.yaml` | 누구나 (PR) | ✅ (코드 아님, 리뷰만) |
| LLM 모델·provider | 환경변수 | DevOps | 재시작만 |
| 새 **데이터 출처** | `PlaceProvider` 구현 1파일 | 개발자 | ✅ |
| 새 **피처**(예: 날씨 적합도) | `features.py` 함수 1개 + 프로필에 weight 키 | 개발자 | ✅ |
| 새 **이동시간 API** | `TravelTimeProvider` 구현 1파일 | 개발자 | ✅ |

**이를 보장하는 장치**
1. 코드에 지역명·장소명 리터럴이 없다 — CI에서 `grep`으로 seed 디렉터리 밖의 지역 slug 리터럴을 검사.
2. **회귀 테스트**: 임시 디렉터리에 처음 보는 지역 JSON을 만들어 ingest → 코스 생성이 되는지 확인하는 테스트가 CI에 상주(`test_new_region_data_only`).
3. 지역 활성화 **품질 게이트**(역할별 장소 ≥ 15, 가격 보유율 ≥ 60%)를 시스템이 검사 — 데이터만 넣었는데 빈 코스가 나오는 사고 방지.
4. 설정 변경은 전부 버전·`audit_log` 기록 → 즉시 롤백 가능.

## 2. 신규 지역 오픈 런북 (운영자용, 예상 1~2일)

1. Admin › 지역 › **추가**: slug, 이름, 상위 지역, 중심 좌표, 반경, 수집 키워드, TourAPI 지역코드
2. **수집 시작** → 진행률 확인 (보통 20~60분)
3. **장소 승인** 큐 처리 — 신뢰 출처는 자동 승인, 중복 의심만 검토
4. 품질 게이트 미달 역할 확인 → 공공데이터 CSV 업로드 또는 수동 추가
5. **미리보기**: 관리자 전용으로 해당 지역 코스 10건 생성 → 육안 점검
6. **활성화** → 캐시 무효화 자동 → 사용자 노출
7. D+7: 추천 통계에서 슬롯 공백률·저장률 확인

## 3. 코드 품질 체계

| 영역 | 도구 · 규칙 |
|---|---|
| 정적 분석 | Python: `ruff`(lint+format), `mypy --strict`(domain·services) · TS: `eslint`, `tsc --noEmit`, `prettier` |
| 아키텍처 경계 | `import-linter` — domain은 프레임워크 import 금지, controller→repository 직접 호출 금지 |
| 테스트 피라미드 | 단위(도메인, DB 불필요, 수백 개·수 초) > 통합(SQLite/PostGIS 컨테이너 + httpx) > E2E(Playwright 핵심 플로우 5개) |
| 커버리지 | domain ≥ 90%, 전체 ≥ 75%. PR에서 하락 시 차단 |
| 계약 | OpenAPI → `openapi-typescript`로 프론트 타입 생성, `schemathesis`로 응답 검증. 계약 변경이 곧 컴파일 에러 |
| 추천 품질 회귀 | **골든 세트**: 고정 seed 데이터 + 요청 50개의 기대 속성(예산 준수, 역할 순서, 총 이동시간 상한)을 스냅샷 비교. 가중치·알고리즘 PR마다 diff 리포트 |
| 프롬프트 회귀 | 프롬프트 YAML 변경 시 고정 입력 20건에 대해 스키마 적합·금지어·장소명 환각 검사 |
| 리뷰 | CODEOWNERS(domain은 2인 승인), PR 템플릿(변경 이유·테스트·롤백 방법) |
| 커밋 | Conventional Commits → 릴리스 노트 자동 생성 |

## 4. 의존성 · 기술 부채 관리

- **Dependabot** 주 1회 그룹 PR(minor/patch 자동 머지, major는 수동). 보안 패치는 즉시.
- 런타임 업그레이드 주기: Python·Node LTS는 연 1회, Next.js major는 릴리스 후 1분기 관망.
- `uv.lock` / `package-lock.json` 고정, 컨테이너 베이스 이미지 다이제스트 고정 + 월 1회 리빌드.
- 부채는 이슈 라벨 `tech-debt`로 추적, 스프린트 용량의 **20%** 고정 배정.
- **ADR**(Architecture Decision Record)을 `docs/adr/NNNN-*.md`로 남긴다 — "왜 FastAPI인가", "왜 LLM이 점수를 매기지 않는가" 같은 결정의 맥락이 사람이 바뀌어도 남도록.

## 5. 데이터 유지보수

| 작업 | 주기 | 자동화 |
|---|---|---|
| 폐업 감지 | 주 1회 | 90일 미갱신 장소 재조회, 없으면 `closed` |
| 가격 드리프트 | 월 1회 | 물가 반영: 피드백 `actual_spend`와 산출가 괴리 > 15%인 장소 목록 → 재수집 |
| 중복 정리 | 상시 | 유사도 0.6~0.85 큐 |
| 종료 이벤트 | 매일 | `ends_on < today` → `ended` |
| 색인 재구축 | 매핑 변경 시 | 새 인덱스 → alias 스왑(무중단) |
| DB | 주 1회 | `recommendation_log`·`audit_log` 월 파티션 생성/아카이브(S3 Parquet, 13개월 후) |
| 마이그레이션 | 배포마다 | Alembic, **expand → migrate → contract** 3단계로 무중단. 파괴적 변경은 최소 1릴리스 간격 |
| 백업·복구 | 일 1회 스냅샷 + PITR 7일 | **분기 1회 복구 리허설**(RTO 1h / RPO 5m 목표) |

## 6. 운영 프로세스

- **온콜**: 주간 로테이션, 알람 → Slack → 15분 내 미확인 시 전화. 알람마다 런북 링크 필수(`docs/runbooks/`).
- **장애 등급**: P1(코스 생성 불가) 즉시 · P2(일부 지역/기능) 4h · P3(비핵심) 영업일.
- **포스트모템**: P1/P2는 5영업일 내 blameless 문서, 재발 방지 액션은 이슈로 추적.
- **릴리스**: trunk-based, feature flag(PostHog)로 미완성 기능 은닉, 주 2~3회 배포. 금요일 오후 배포 금지.
- **변경 로그**: 사용자 영향 있는 변경은 Admin 공지 + 앱 내 "짠이의 새 소식".

## 7. 문서 유지

| 문서 | 정본 | 갱신 방법 |
|---|---|---|
| API | FastAPI OpenAPI | 코드에서 자동 생성 (수기 문서는 의도만) |
| ERD | Alembic 모델 | CI에서 `eralchemy`로 다이어그램 재생성 |
| 인프라 | Terraform | `terraform-docs` 자동 |
| 아키텍처·결정 | `docs/`, `docs/adr/` | PR과 함께 |
| 런북 | `docs/runbooks/` | 장애마다 갱신 |
