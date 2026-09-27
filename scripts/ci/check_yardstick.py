"""CI: 잣대 잠금 파일을 바꾼 커밋을 검사한다 (docs/64 R17 ②).

    python scripts/ci/check_yardstick.py <base> <head>

<base>..<head> 의 커밋마다, `apps/api/data/eval/yardstick.lock.json` 을 바꿨으면:
  1. 커밋 메시지에 `Yardstick-Approved: R<번호>` 가 있어야 한다(docs/64 의 창업자 승인 줄).
  2. 같은 커밋이 엔진 · 데이터 · 서비스 코드를 바꾸면 안 된다 — 허용: 잠금 파일, 점수표 코드(concept.py ·
     yardstick.py), 그 테스트, docs.
어기면 실패(종료 코드 1). 잠금 파일을 안 바꾼 커밋은 보지 않는다 — 코드와 잠금의 일치는 pytest 가 본다.
"""

from __future__ import annotations

import re
import subprocess
import sys

LOCK = "apps/api/data/eval/yardstick.lock.json"
ALLOWED = (
    LOCK,
    "apps/api/app/evaluation/concept.py",
    "apps/api/app/evaluation/yardstick.py",
    "apps/api/tests/unit/test_concept_scorecard.py",
    "apps/api/tests/unit/test_yardstick.py",
    "docs/",
)
TRAILER = re.compile(r"^Yardstick-Approved:\s*R\d+", re.MULTILINE)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main(base: str, head: str) -> int:
    if set(base) <= {"0"}:  # a new branch push: nothing before it to compare
        base = git("rev-list", "--max-parents=0", head).split()[0]
    failures: list[str] = []
    for sha in git("rev-list", f"{base}..{head}").split():
        files = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).split("\n")
        files = [f for f in files if f]
        if LOCK not in files:
            continue
        msg = git("log", "-1", "--format=%B", sha)
        short = sha[:7]
        if not TRAILER.search(msg):
            failures.append(f"{short}: 잠금 파일을 바꿨는데 `Yardstick-Approved: R<번호>` 가 없다")
        others = [f for f in files if not f.startswith(ALLOWED)]
        if others:
            failures.append(f"{short}: 잣대와 함께 바뀌면 안 되는 파일 — " + ", ".join(others))
    if failures:
        print("잣대 검사 실패 (docs/64 R17):\n" + "\n".join(failures))
        return 1
    print("잣대 검사 통과")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
