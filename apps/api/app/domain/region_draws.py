"""Why people come to a neighbourhood at all (data/regions/draws.json): the dish they cross the city for,
the sight they came to see. Written by hand for the hotspots; everywhere else the signs speak alone.

These words and names only count where the neighbourhood really has them — a word no shop here carries
on its sign, or a sight no place within reach is called, is dropped (signature_service.curate).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DRAWS_PATH = Path(__file__).resolve().parents[2] / "data" / "regions" / "draws.json"


@dataclass(frozen=True, slots=True)
class Draws:
    eat: tuple[str, ...] = ()
    see: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def region_draws(path: Path = DRAWS_PATH) -> dict[str, Draws]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        slug: Draws(tuple(v.get("eat") or ()), tuple(v.get("see") or ()))
        for slug, v in data.items()
        if not slug.startswith("_") and isinstance(v, dict)
    }


def draws_for(slug: str | None) -> Draws | None:
    found = region_draws().get(slug or "")
    return found if found and (found.eat or found.see) else None
