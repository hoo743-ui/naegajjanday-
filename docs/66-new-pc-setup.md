# 66. 다른 PC 에서 이어 하기 (2026-09-27)

git 은 코드 · 문서만 옮긴다. **env(키) · Claude 메모리 · 로컬 전국 DB** 는 스크립트 두 개로 옮긴다.

## 옛 PC (한 번)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\migrate\export.ps1          # DB 포함(약 1.2GB)
powershell -ExecutionPolicy Bypass -File scripts\migrate\export.ps1 -NoDb    # DB 빼고
```

`%OneDrive%\naegajjanday-migrate\` 에 `env\ · memory\ · db\ · README.txt` 가 생긴다. **OneDrive 업로드가 끝날 때까지** 기다린다.
이 폴더에는 API 키가 들어 있다 — 공유하지 말고, 새 PC 에서 옮긴 뒤 지운다.

## 새 PC

1. 도구: Git · Node 22 · Python 3.13 · uv · Chrome (없으면 `import.ps1` 이 `winget install …` 명령을 알려 준다)
2. **OneDrive 밖에** 받는다 — OneDrive 안이면 `.next` 가 깨지고 탐색이 느리다.
   ```powershell
   git clone https://github.com/hoo743-ui/naegajjanday-.git C:\dev\naegajjanday
   cd C:\dev\naegajjanday
   powershell -ExecutionPolicy Bypass -File scripts\migrate\import.ps1
   ```
   하는 일:
   - `apps\api\.env` · `apps\web\.env.local` 을 제자리에, `DATABASE_URL` 을 이 PC 의 `%LOCALAPPDATA%` 경로로 고친다
   - Claude 메모리를 이 저장소 경로의 프로젝트 폴더(`%USERPROFILE%\.claude\projects\<경로를 '-' 로 바꾼 이름>\memory`)에
   - 전국 DB 와 점수표 기록을 `%LOCALAPPDATA%\naegajjanday\` 에
   - `uv sync` · `data-sync` · `npm install`
   - 이미 있는 파일은 덮지 않는다(`-Force` 면 `*.bak-<시각>` 으로 남기고 바꾼다). `-SkipInstall` 은 설치 생략.
3. Claude Code 를 저장소 폴더에서 열고: **"docs/PROGRESS.md 맨 위부터 이어서"**.
4. 멈춘 작업물: `git fetch` 후 `git switch wip/r18-children` 또는 `wip/16-mealtime` — 검토 안 된 초안, main 아님.
5. 되면 `%OneDrive%\naegajjanday-migrate` 를 지운다.

## 따라오지 않는 것
- 옛 PC 의 `.claude\worktrees\*`(에이전트 작업 공간) — 필요한 것은 `wip/*` 브랜치로 올려 두었다.
- 옛 PC 루트의 `screenshots\` · `apps\web\x\` · 디자인 예시 png — git 에 없지만 저장소 폴더가 OneDrive 안이라 OneDrive 로 이미 동기화된다(새 PC 의 OneDrive 폴더에서 보면 된다). 107MB 라 git 에는 올리지 않았다.
- 세션 크론(3시간 루프)은 Claude 세션이 끝나면 사라진다 — 새 세션에서 다시 켤지 정한다(docs/64: 검증 틀이 먼저).
