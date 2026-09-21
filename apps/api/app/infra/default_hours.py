"""Category-level default opening hours for places that have none of their own.

Bulk public data carries no opening hours, so the engine treated every one of the ~800k places as
"always open" and happily sent people to a museum at 20:30. The table lives in
`data/hours/default_hours.json` (DATA — edit, restart). A place's real hours always win.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
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
    def __init__(self, table: Mapping[str, Any]) -> None:
        self._periods = {code: periods_from(spec) for code, spec in table.items()}

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
    return DefaultHours(json.loads(path.read_text(encoding="utf-8")).get("by_category", {}))
