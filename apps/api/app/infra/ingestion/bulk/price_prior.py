"""Estimated price per person for places without menu data (`data/bulk/price_prior.json`).

prior = typical spend (Seoul) × regional cost factor, where "typical spend" is looked up as
  1. a **name rule** — brands and formats whose price level is known from the name alone
     (a coin karaoke is not a regular karaoke room; a 2,000-won-americano chain is not an average café),
  2. the source's own sub-category code,
  3. our category (walking up: "food.korean" → "food").

Always stored with `place.price_is_estimated = True`; measured menu prices never go through this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class NameRule:
    contains: tuple[str, ...]
    categories: tuple[str, ...]  # category-code prefixes; empty = any category
    price: int

    def matches(self, compact_name: str, category_code: str) -> bool:
        if self.categories and not any(
            category_code == c or category_code.startswith(c + ".") for c in self.categories
        ):
            return False
        return any(word in compact_name for word in self.contains)


@dataclass(frozen=True, slots=True)
class PricePrior:
    by_source_code: Mapping[str, int]
    by_category: Mapping[str, int]
    sido_factor: Mapping[str, float]
    round_to: int = 100
    name_rules: tuple[NameRule, ...] = field(default_factory=tuple)

    @classmethod
    def from_data(cls, prior: Mapping[str, Any], regions_spec: Mapping[str, Any]) -> PricePrior:
        factors: dict[str, float] = {}
        for sido in regions_spec.get("sido", []):
            factor = float(sido.get("cost_factor", 1.0))
            for name in (sido["name"], *sido.get("aliases", [])):
                factors[name] = factor
        return cls(
            by_source_code={k: int(v) for k, v in prior.get("by_semas_code", {}).items()},
            by_category={k: int(v) for k, v in prior.get("by_category", {}).items()},
            sido_factor=factors,
            round_to=int(prior.get("round_to", 100)),
            name_rules=tuple(
                NameRule(
                    contains=tuple(str(w).replace(" ", "").upper() for w in rule["contains"]),
                    categories=tuple(rule.get("categories", ())),
                    price=int(rule["price"]),
                )
                for rule in prior.get("name_rules", [])
            ),
        )

    def base(self, category_code: str, source_code: str | None = None, name: str | None = None) -> int | None:
        if name:
            compact = name.replace(" ", "").upper()
            for rule in self.name_rules:  # first match wins — order the data from specific to general
                if rule.matches(compact, category_code):
                    return rule.price
        if source_code and source_code in self.by_source_code:
            return self.by_source_code[source_code]
        code = category_code
        while code:  # "food.korean" → "food"
            if code in self.by_category:
                return self.by_category[code]
            code = code.rpartition(".")[0]
        return None

    def estimate(
        self,
        category_code: str,
        sido: str | None,
        source_code: str | None = None,
        name: str | None = None,
    ) -> int | None:
        base = self.base(category_code, source_code, name)
        if base is None:
            return None
        value = base * self.sido_factor.get(sido or "", 1.0)
        return int(round(value / self.round_to) * self.round_to)
