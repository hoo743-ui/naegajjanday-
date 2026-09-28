"""잣대 고정 (docs/64 R17 ②) — 점수표 지표의 목표 · 방향 · 가중치를 잠금 파일로 묶는다.

잠금 파일 `data/eval/yardstick.lock.json` 은 METRICS 의 "무엇이 합격인가"를 그대로 적은 사본이다.
테스트(tests/unit/test_yardstick.py)가 코드와 잠금 파일이 같은지 본다 — 다르면 실패.
잠금 파일을 바꾸는 커밋은 CI(scripts/ci/check_yardstick.py)가 따로 본다:
  - 엔진 · 데이터(app/domain · app/services · data/recommendation · data/regions …)를 같이 바꾸면 실패
  - 커밋 메시지에 `Yardstick-Approved: R<번호>`(docs/64 의 창업자 승인 줄)가 없으면 실패
그래서 "고친 뒤 잣대를 옮겨 통과"가 한 커밋에서 일어날 수 없다.

    uv run python -m app.evaluation.yardstick           # 코드와 잠금 파일 차이 보기
    uv run python -m app.evaluation.yardstick --write   # 잠금 파일 다시 쓰기(승인된 변경만)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

LOCK_PATH = Path(__file__).resolve().parents[2] / "data" / "eval" / "yardstick.lock.json"
# 합격 여부를 바꾸는 필드만 — 라벨(글자)은 바꿔도 잣대가 아니다
FIELDS = ("direction", "target", "kind", "scale", "weight", "half", "floor_only")
# 일관성 불변식의 문턱 (docs/65 §3 · §5, 창업자 승인 2026-09-28): 점수표 지표와 같은 규칙으로 잠근다 —
# 바꾸려면 창업자 승인 후 엔진 변경과 다른 커밋에서 `--write`. tests/metamorphic 이 여기서 읽는다.
#   I3: 출발 시각 ±10분 → 장소의 ≥70% 유지 · I7: 인원만 바꿈(2→3, 1인 예산 같게) → 장소 종류 구성 유지
INVARIANT_THRESHOLDS: dict[str, float] = {
    "I3_start_shift_keep_share": 0.7,
    "I7_party_kind_keep_share": 0.7,
}


def current() -> dict[str, dict[str, Any]]:
    from app.evaluation.concept import METRICS

    return {m.id: {f: getattr(m, f) for f in FIELDS} for m in METRICS}


def locked() -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["metrics"]
    return data


def locked_invariants() -> dict[str, float]:
    data: dict[str, float] = json.loads(LOCK_PATH.read_text(encoding="utf-8")).get("invariants", {})
    return data


def diff() -> list[str]:
    """코드와 잠금 파일의 차이, 사람이 읽는 줄로. 빈 목록이면 같다."""
    code, lock = current(), locked()
    out: list[str] = []
    inv_code, inv_lock = INVARIANT_THRESHOLDS, locked_invariants()
    for key in sorted(inv_code.keys() | inv_lock.keys()):
        if inv_code.get(key) != inv_lock.get(key):
            out.append(f"~ invariants.{key}: 잠금 {inv_lock.get(key)!r} → 코드 {inv_code.get(key)!r}")
    for mid in sorted(code.keys() - lock.keys()):
        out.append(f"+ {mid}: 잠금 파일에 없는 새 지표 {code[mid]}")
    for mid in sorted(lock.keys() - code.keys()):
        out.append(f"- {mid}: 코드에서 사라진 지표")
    for mid in sorted(code.keys() & lock.keys()):
        for f in FIELDS:
            if code[mid][f] != lock[mid].get(f):
                out.append(f"~ {mid}.{f}: 잠금 {lock[mid].get(f)!r} → 코드 {code[mid][f]!r}")
    return out


def write() -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "_note": "잣대 잠금 — 손으로 고치지 말 것. `python -m app.evaluation.yardstick --write` 로만, "
        "창업자 승인(docs/64) 후 엔진 · 데이터 변경과 다른 커밋에서, 메시지에 `Yardstick-Approved: R<번호>`.",
        "metrics": current(),
        "invariants": dict(INVARIANT_THRESHOLDS),
    }
    text = json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    LOCK_PATH.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="잠금 파일을 지금 코드로 다시 쓴다")
    args = ap.parse_args()
    if args.write:
        write()
        print(f"썼다: {LOCK_PATH}")
        return 0
    lines = diff()
    print("\n".join(lines) if lines else "코드와 잠금 파일이 같다")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())
