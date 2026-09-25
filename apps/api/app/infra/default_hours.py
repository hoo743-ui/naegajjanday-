"""Category-level default opening hours for places that have none of their own.

Bulk public data carries no opening hours, so the engine treated every one of the ~800k places as
"always open" and happily sent people to a museum at 20:30. The table lives in
`data/hours/default_hours.json` (DATA — edit, restart). A place's real hours always win.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import API_ROOT
from app.domain.models import OpeningPeriod

HOURS_PATH = API_ROOT / "data" / "hours" / "default_hours.json"
DAYS = range(7)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def periods_from(spec: Mapping[str, Any] | str | None) -> tuple[OpeningPeriod, ...]:
    if not isinstance(spec, Mapping):
        return ()  # "always" / unknown → no restriction
    open_min, close_min = _minutes(str(spec["open"])), _minutes(str(spec["close"]))
    if close_min <= open_min:
        close_min += 1440  # past midnight
    closed = set(spec.get("closed_dow", []))
    return tuple(
        OpeningPeriod(d, 0, 0, is_closed=True) if d in closed else OpeningPeriod(d, open_min, close_min)
        for d in DAYS
    )


class DefaultHours:
    def __init__(
        self,
        table: Mapping[str, Any],
        by_name: Sequence[Mapping[str, Any]] = (),
        in_building: Mapping[str, Any] | None = None,
    ) -> None:
        self._periods = {code: periods_from(spec) for code, spec in table.items()}
        building = in_building or {}
        self._floor = re.compile(str(building["pattern"])) if building.get("pattern") else None
        self._building = periods_from(building.get("hours"))
        self._building_by_category = {
            c: periods_from(h) for c, h in (building.get("by_category") or {}).items()
        }
        # what the sign itself says ("24시 …") comes before what the trade usually does
        self._by_name = [
            (tuple(rule["words"]), tuple(rule.get("categories") or ()), periods_from(rule.get("hours")))
            for rule in by_name
        ]

    def for_place(
        self, category_code: str, name: str, address: str | None = None
    ) -> tuple[OpeningPeriod, ...]:
        found = self._by_name_or_category(category_code, name)
        # "always open" (a street, a park, a view) with a floor in its address is inside a building
        if not found and address and self._floor and self._floor.search(address):
            root = category_code.split(".")[0]
            return self._building_by_category.get(root) or self._building
        return found

    def _by_name_or_category(self, category_code: str, name: str) -> tuple[OpeningPeriod, ...]:
        for words, categories, periods in self._by_name:
            if categories and not any(
                category_code == c or category_code.startswith(f"{c}.") for c in categories
            ):
                continue
            if any(word in name for word in words):
                return periods
        return self.for_category(category_code)

    def for_category(self, category_code: str) -> tuple[OpeningPeriod, ...]:
        parts = category_code.split(".")
        for depth in range(len(parts), 0, -1):  # most specific first
            key = ".".join(parts[:depth])
            if key in self._periods:
                return self._periods[key]
        return ()


@lru_cache(maxsize=1)
def get_default_hours(path: Path = HOURS_PATH) -> DefaultHours:
    if not path.exists():
        return DefaultHours({})
    data = json.loads(path.read_text(encoding="utf-8"))
    return DefaultHours(data.get("by_category", {}), data.get("by_name", []), data.get("in_building"))
