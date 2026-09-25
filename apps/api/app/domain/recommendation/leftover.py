"""Money left over, said out loud (docs/49).

A course that spends 16,000 of a 60,000 won budget without a word reads as "did it even try?". The band
says how much is left in the user's terms; the reason says why, so the screen never shows a large
leftover without one. Thresholds and sentences are data (suggestions.json › leftover).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

BUFFER, SPENDABLE, UNDERSPENT = "buffer", "spendable", "underspent"


@dataclass(frozen=True, slots=True)
class Leftover:
    band: str  # buffer | spendable | underspent
    reason: str | None
    text: str | None


def assess(
    *,
    budget: int,
    price: int,
    prices: Sequence[int],
    night: bool,
    asked_value: bool,
    slot_empty: bool,
    rules: Mapping[str, Any],
) -> Leftover:
    left = max(0, budget - price)
    share = left / budget if budget > 0 else 0.0
    if share < float(rules.get("buffer_below", 0.15)):
        band = BUFFER
    elif share < float(rules.get("explain_from", 0.4)):
        band = SPENDABLE
    else:
        band = UNDERSPENT
    reason: str | None = None
    if band != BUFFER:
        free = sum(1 for p in prices if p <= 0)
        if asked_value:
            reason = "USER_ASKED_VALUE"  # the user asked for cheaper: what is left is the point
        elif night:
            reason = "FEW_OPEN_AT_THIS_HOUR"
        elif prices and free * 2 >= len(prices):
            reason = "FREE_HEAVY"
        elif slot_empty or band == UNDERSPENT:
            reason = "NOTHING_WORTH_IT"  # a day that still spent under 60 % was already topped up once
        else:
            # no evidence of why (prices are category averages): say what is left, not a story about it —
            # "이 동네는 가격이 낮은 편이라" was a guess shown on most courses (2026-09-25)
            reason = "ROOM_TO_ADD"
    texts: Mapping[str, str] = rules.get("reasons") or {}
    text = texts.get(reason or "") if reason else texts.get("_buffer") if left > 0 else None
    return Leftover(band, reason, text.format(left=f"{left:,}원") if text else None)
