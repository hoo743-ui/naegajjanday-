"""구경하는 가게 (docs/63): what the page says about a shop stop, and the small age nudge.

A shop is an ATTRACTION-role stop (a browse between a meal and a café) whose category is `shop.*`. Two things
live here, both from data:

- `why_line`: the card's one line — what the shop sells (its brand when the name carries one, from
  data/bulk/shop_rules.json) and how long a browse takes. Nothing the data does not hold: no "popular",
  no "20대가 많이 가는".
- `taste_pull`: an assumed (not measured) age taste, read only from context the request already has — a
  campus anchor or campus purpose, a date scene. data/recommendation/shops.json › age_taste says why.
- `with_browse_slot`: an "if it fits" slot after the meal that takes shops only (Slot.family) — when the
  option is on, or unasked on a friends' or a date's afternoon where browsing is the neighbourhood's draw
  (draws.json › shop, docs/59 #12); the neighbourhood's own sight keeps its slot; no shop near, no browse.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import Slot, Template

DATA = Path(__file__).resolve().parents[3] / "data"
SHOPS_PATH = DATA / "recommendation" / "shops.json"
SHOP_RULES_PATH = DATA / "bulk" / "shop_rules.json"
PREFIX = "shop"
SHOP_EXTRA = "SHOP"  # data/recommendation/extra_roles.json › SHOP (the 소품샵 · 캐릭터샵 option)


@lru_cache(maxsize=1)
def shop_texts(path: Path = SHOPS_PATH) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=1)
def _brands(path: Path = SHOP_RULES_PATH) -> tuple[tuple[str, str, str], ...]:
    """(compact brand, kind, label), longest first so "모나미스테이션" wins over a shorter word."""
    rules = json.loads(path.read_text(encoding="utf-8"))
    out = [
        (_compact(brand), str(kind["category"]), str(label))
        for kind in rules.get("types") or ()
        for brand, label in (kind.get("brands") or {}).items()
    ]
    return tuple(sorted(out, key=lambda b: -len(b[0])))


def _compact(text: str) -> str:
    return text.replace(" ", "").upper()


def is_shop(category_code: str) -> bool:
    return category_code == PREFIX or category_code.startswith(PREFIX + ".")


def brand_of(name: str) -> tuple[str, str] | None:
    """(kind of shop, what the brand is — "산리오 캐릭터") when the name carries a listed brand."""
    compact = _compact(name)
    return next(((kind, label) for brand, kind, label in _brands() if brand in compact), None)


def _kind(category_code: str) -> Mapping[str, str]:
    kinds: Mapping[str, Mapping[str, str]] = shop_texts()["kinds"]
    return kinds.get(category_code) or kinds[PREFIX]


def why_line(name: str, category_code: str) -> str:
    """ "카카오프렌즈 캐릭터 플래그십 · 구경만 해도 20~30분" / "빈티지 · 구제 가게 · 구경 30분 남짓"."""
    texts = shop_texts()
    kind = _kind(category_code)
    brand = brand_of(name)
    if brand is not None:
        compact = _compact(name)
        flagship = any(_compact(w) in compact for w in texts.get("flagship_words") or ())
        line = str(texts["flagship_line" if flagship else "brand_line"])
        return line.format(brand=brand[1], browse=kind["browse"])
    return f"{kind['label']} · {kind['browse']}"


def _minute(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def with_browse_slot(
    templates: Sequence[Template],
    purpose_code: str,
    start: datetime,
    *,
    asked: bool = False,
    drawn: Sequence[str] = (),
) -> list[Template]:
    """An optional shops-only slot right after the meal (or first). Templates without it come back as they
    were.

    `asked` (the 소품샵 · 캐릭터샵 option): any purpose, any hour, any shop — when no shop is open near, the
    page says so (EXTRA_UNAVAILABLE). Unasked (docs/59 #12), only where browsing is the neighbourhood's
    draw (`drawn`, draws.json › shop) and only for the purposes and start hours of shops.json › browse_slot:
    the slot then takes that kind of shop (one kind listed) and drops silently when none is open near.
    Either way the neighbourhood's own sight keeps its slot."""
    rule: Mapping[str, Any] = shop_texts().get("browse_slot") or {}
    at_min = start.hour * 60 + start.minute
    if not asked and (
        not drawn
        or purpose_code not in (rule.get("purposes") or ())
        or not _minute(str(rule["start_from"])) <= at_min <= _minute(str(rule["start_until"]))
    ):
        return list(templates)
    family = str(rule["family"]) if asked or len(drawn) != 1 else str(drawn[0])
    share, after = float(rule.get("share", 0.0)), str(rule.get("after") or "")
    out: list[Template] = []
    for template in templates:
        slots = list(template.slots)
        if any(s.family and is_shop(s.family) for s in slots):
            out.append(template)
            continue
        at = next((i for i, s in enumerate(slots) if s.course_role == after), 0)
        slots = [replace(s, budget_share=s.budget_share * (1.0 - share)) for s in slots]
        browse = Slot(
            position=0, course_role="ATTRACTION", budget_share=share, is_optional=True, family=family
        )
        slots.insert(at + 1, browse)
        slots = [replace(s, position=i + 1) for i, s in enumerate(slots)]
        out.append(replace(template, slots=tuple(slots)))
    return out


def age_group(purpose_code: str, scene: str | None, anchored: bool) -> str | None:
    """Which (assumed) age group the request's own context points to — None when it says nothing."""
    ctx: Mapping[str, Any] = shop_texts()["age_taste"]["contexts"]
    if anchored and ctx.get("anchor"):
        return str(ctx["anchor"])
    if purpose_code in (ctx.get("purposes") or {}):
        return str(ctx["purposes"][purpose_code])
    key = f"{purpose_code}.{scene}" if scene else None
    if key and key in (ctx.get("scenes") or {}):
        return str(ctx["scenes"][key])
    return None


def taste_pull(purpose_code: str, scene: str | None, anchored: bool) -> dict[str, float]:
    """{"cat:shop.vintage": 0.04, …} for the scorer's trait pull (scorer.trait_pull), or {}."""
    group = age_group(purpose_code, scene, anchored)
    if group is None:
        return {}
    taste: Mapping[str, Any] = shop_texts()["age_taste"]
    pull = float(taste.get("pull", 0.0))
    weights: Mapping[str, float] = taste["groups"].get(group) or {}
    return {f"cat:{code}": round(pull * float(w), 4) for code, w in weights.items() if w}
