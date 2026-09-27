"""정리 보고서 — 무엇을 지워도 되는지 보여 주기만 한다 (docs/64 R3, 창업자 결정 B).

이 스크립트는 **아무것도 지우지 않는다.** 지워도 되는 것과 그 이유 · 크기를 출력하고,
창업자가 직접 실행할 삭제 명령을 마지막에 적어 준다(PowerShell 에 붙여 넣거나 Claude 프롬프트에 `! ` 로).

    python scripts/housekeeping.py            # 보고서
    python scripts/housekeeping.py --sizes    # 폴더 크기까지(OneDrive 라 느림)
    python scripts/housekeeping.py --code     # 안 쓰는 Python 코드 후보(vulture, 보고만)

지워도 된다고 보는 worktree(.claude/worktrees/agent-*):
  - 추적 파일에 커밋 안 된 변경이 없고,
  - 그 브랜치의 커밋이 모두 origin/main 에 들어갔고(같은 내용으로 rebase 된 것 포함 — `git cherry`),
  - 잠겨 있지 않고(`git worktree lock`),
  - 최근 60분 안에 바뀐 파일이 없다(지금 돌고 있는 에이전트를 건드리지 않으려고).
worktree 안의 apps/web/node_modules 가 연결(junction)이면 삭제 명령은 **연결부터 끊는다** —
순서를 틀리면 부모 저장소의 node_modules 까지 지워질 수 있다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDLE_MINUTES = 60
SKIP_DIRS = {".venv", "node_modules", ".next", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def git(*args: str, cwd: Path = ROOT) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.stdout.strip()


def _nt_junction(p: Path) -> bool:
    if os.name != "nt" or not p.exists():
        return False
    try:
        return bool(os.lstat(p).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (OSError, AttributeError):
        return False


def newest_mtime(path: Path) -> float:
    """가장 최근에 바뀐 파일 시각 — 무거운 폴더(.venv · node_modules …)는 건너뛴다."""
    newest = path.stat().st_mtime
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            try:
                newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
            except OSError:
                pass
    return newest


def dir_size(path: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not _nt_junction(Path(dirpath) / d)]
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


@dataclass
class Worktree:
    path: Path
    branch: str
    locked: bool
    reasons: list[str] = field(default_factory=list)
    size: int | None = None

    @property
    def removable(self) -> bool:
        return not self.reasons


def list_worktrees() -> list[Worktree]:
    trees: list[Worktree] = []
    cur: dict[str, str] = {}
    for line in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if cur.get("worktree") and Path(cur["worktree"]).resolve() != ROOT:
                trees.append(Worktree(Path(cur["worktree"]), cur.get("branch", "").removeprefix("refs/heads/"), "locked" in cur))
            cur = {}
            continue
        key, _, val = line.partition(" ")
        cur[key] = val
    return trees


def judge(wt: Worktree, sizes: bool) -> None:
    if not wt.path.exists():
        wt.reasons.append("폴더 없음(git worktree prune 대상)")
        return
    if wt.locked:
        wt.reasons.append("잠김")
    # 새로 만든 파일(추적 안 됨)도 작업물이다 — .gitignore 된 것(.env · .venv …)만 빼고 센다.
    if git("status", "--porcelain", cwd=wt.path):
        wt.reasons.append("커밋 안 된 변경 · 새 파일")
    unmerged = [ln for ln in git("cherry", "origin/main", "HEAD", cwd=wt.path).splitlines() if ln.startswith("+")]
    if unmerged:
        wt.reasons.append(f"main 에 없는 커밋 {len(unmerged)}개")
    idle = (time.time() - newest_mtime(wt.path)) / 60
    if idle < IDLE_MINUTES:
        wt.reasons.append(f"{idle:.0f}분 전에 바뀜(작업 중일 수 있음)")
    if sizes:
        wt.size = dir_size(wt.path)


def remove_commands(wt: Worktree) -> list[str]:
    cmds = []
    nm = wt.path / "apps" / "web" / "node_modules"
    if _nt_junction(nm) or nm.is_symlink():
        cmds.append(f'cmd /c rmdir "{nm}"   # 연결만 끊는다 — 먼저')
    cmds.append(f'git worktree remove --force "{wt.path}"')
    if wt.branch:
        cmds.append(f"git branch -D {wt.branch}")
    return cmds


def eval_history(keep: int) -> tuple[list[Path], int]:
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "naegajjanday" / "eval" / "concept"
    if not base.is_dir():
        return [], 0
    runs = sorted((p for p in base.glob("2*.json")), key=lambda p: p.stat().st_mtime, reverse=True)
    old = runs[keep:]
    return old, sum(p.stat().st_size for p in old)


def big_scratch(min_mb: int) -> list[tuple[Path, int]]:
    tmp = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" / "claude"
    found: list[tuple[Path, int]] = []
    if not tmp.is_dir():
        return found
    for p in tmp.rglob("*"):
        try:
            if p.is_file() and p.stat().st_size >= min_mb * 1024 * 1024:
                found.append((p, p.stat().st_size))
        except OSError:
            pass
    return sorted(found, key=lambda x: -x[1])


def listening(ports: tuple[int, ...]) -> list[str]:
    if os.name != "nt":
        return []
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace").stdout
    hits = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and any(parts[1].endswith(f":{p}") for p in ports):
            hits.append(f"{parts[1]} pid {parts[4]}")
    return hits


def dead_code() -> str:
    api = ROOT / "apps" / "api"
    res = subprocess.run(["uvx", "vulture", "app", "--min-confidence", "80"], cwd=api, capture_output=True, text=True, errors="replace")
    return (res.stdout or res.stderr).strip() or "(후보 없음)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", action="store_true", help="worktree 폴더 크기 재기(느림)")
    ap.add_argument("--code", action="store_true", help="안 쓰는 Python 코드 후보(vulture)")
    ap.add_argument("--keep-eval", type=int, default=20, help="남길 점수표 실행 기록 수(이름 붙은 것은 늘 남김)")
    ap.add_argument("--scratch-mb", type=int, default=100, help="이 크기 이상 scratch 파일만 보고")
    args = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    git("fetch", "-q", "origin")
    print("# 정리 보고서 — 아무것도 지우지 않았다\n")

    trees = list_worktrees()
    for wt in trees:
        judge(wt, args.sizes)
    ok = [w for w in trees if w.removable]
    print(f"## worktree {len(trees)}개 — 지워도 됨 {len(ok)} · 남김 {len(trees) - len(ok)}")
    for wt in trees:
        size = f" · {human(wt.size)}" if wt.size is not None else ""
        verdict = "지워도 됨" if wt.removable else "남김: " + ", ".join(wt.reasons)
        print(f"- {wt.path.name} ({wt.branch or '-'}){size} — {verdict}")

    registered = {w.path.resolve() for w in trees}
    wt_dir = ROOT / ".claude" / "worktrees"
    orphans = [p for p in wt_dir.iterdir() if p.is_dir() and p.resolve() not in registered] if wt_dir.is_dir() else []
    print(f"\n## git 이 모르는 남은 폴더(.claude/worktrees) {len(orphans)}개 — worktree 등록이 풀린 찌꺼기")
    for p in orphans:
        print(f"- {p.name}")

    old, old_bytes = eval_history(args.keep_eval)
    print(f"\n## 점수표 실행 기록 — 최근 {args.keep_eval}개 · 이름 붙은 것은 남김, 오래된 {len(old)}개 ({human(old_bytes)})")

    big = big_scratch(args.scratch_mb)
    print(f"\n## Claude 임시 폴더의 큰 파일(≥{args.scratch_mb}MB) {len(big)}개")
    for p, n in big[:20]:
        print(f"- {human(n)} {p}")

    ports = listening((3000, 8000))
    print("\n## 떠 있는 개발 서버(3000/8000): " + (", ".join(ports) if ports else "없음") + " — 끄는 것은 직접")

    if args.code:
        print("\n## 안 쓰는 Python 코드 후보(vulture ≥80%) — 지우기 전에 테스트 · 점수표로 확인\n" + dead_code())

    print("\n## 창업자가 실행할 삭제 명령 (저장소 루트에서, 위에서부터 차례로)")
    if not ok and not old and not orphans:
        print("(지울 것 없음)")
    for wt in ok:
        for c in remove_commands(wt):
            print(c)
    for p in orphans:
        nm = p / "apps" / "web" / "node_modules"
        if _nt_junction(nm):
            print(f'cmd /c rmdir "{nm}"   # 연결만 끊는다 — 먼저')
        print(f'Remove-Item -Recurse -Force "{p}"')
    if old:
        print("# 오래된 점수표 기록:")
        for p in old:
            print(f'Remove-Item "{p}"')
    print("git worktree prune")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
