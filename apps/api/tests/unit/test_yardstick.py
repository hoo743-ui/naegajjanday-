"""잣대 잠금(docs/64 R17 ②): 점수표 지표의 목표 · 방향 · 가중치가 잠금 파일과 같아야 한다."""

from __future__ import annotations

from app.evaluation import yardstick


def test_metrics_match_the_locked_yardstick() -> None:
    lines = yardstick.diff()
    assert not lines, (
        "점수표의 잣대가 잠금 파일과 다르다 — 목표를 바꾸려면 창업자 승인(docs/64) 후 "
        "엔진 변경과 다른 커밋에서 `python -m app.evaluation.yardstick --write` 하고 "
        "메시지에 `Yardstick-Approved: R<번호>`:\n" + "\n".join(lines)
    )
