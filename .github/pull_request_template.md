## 무엇을 / 왜 (What & why)

<!-- 변경 요약과 배경. 관련 이슈: Closes #123 -->

## 변경 범위

- [ ] `apps/web`
- [ ] `apps/api`
- [ ] `infra/` (Terraform / Docker)
- [ ] `.github/` (CI/CD)
- [ ] `docs/`

## 어떻게 확인했나요? (How was this tested)

<!-- 실행한 명령, 스크린샷, Vercel 미리보기 URL 등 -->

- [ ] `make lint` / `.\scripts\dev.ps1 lint`
- [ ] `make test` / `.\scripts\dev.ps1 test`

## 체크리스트

- [ ] API 계약을 바꿨다면 `docs/03-api-spec.md` 와 프론트 타입(`npm run gen:api`)을 갱신했다
- [ ] DB 스키마를 바꿨다면 Alembic 마이그레이션이 있고, **이전 버전 앱과도 호환**된다 (expand → deploy → contract; 배포 롤백 시 마이그레이션은 되돌리지 않음)
- [ ] 새 환경변수 / 시크릿은 `.env.example`, `infra/terraform/modules/stack` (`app_secret_keys` 또는 `api_environment`) 에 반영했고, 시크릿 값은 Secrets Manager 에 **먼저** 넣었다
- [ ] 추천 로직(스코어링·템플릿)을 바꿨다면 `docs/06-recommendation-algorithm.md` 와 테스트를 갱신했다
- [ ] 인프라 변경이면 `terraform plan` 결과(staging)를 아래에 붙였다
- [ ] 비밀값·개인정보가 코드, 로그, 스크린샷에 없다

## 배포 메모 (Deploy notes)

<!-- 순서가 필요한 작업, 수동 작업, 롤백 방법, feature flag 등. 없으면 "없음" -->

<details>
<summary>terraform plan</summary>

```text

```

</details>
