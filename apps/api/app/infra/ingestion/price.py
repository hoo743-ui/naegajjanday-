"""price_per_person from the menu median (ERD `place.price_per_person`)."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from app.infra.ingestion.base import NormalizedMenu

PRICE_TIER_BOUNDS = (10_000, 20_000, 40_000)  # tier 1 ≤ 10k < tier 2 ≤ 20k < tier 3 ≤ 40k < tier 4
SIDE_MENU_RATIO = 0.35  # drinks / sides far below the signature price are not a "per person" spend


def price_per_person(menus: Sequence[NormalizedMenu]) -> int | None:
    prices = sorted(m.price for m in menus if m.price > 0)
    if not prices:
        return None
    anchor = max((m.price for m in menus if m.is_signature), default=prices[-1])
    mains = [p for p in prices if p >= anchor * SIDE_MENU_RATIO] or prices
    return int(round(median(mains), -2))


def price_tier(price: int | None, is_free: bool) -> int:
    if is_free or not price:
        return 1
    for tier, bound in enumerate(PRICE_TIER_BOUNDS, start=1):
        if price <= bound:
            return tier
    return 4
