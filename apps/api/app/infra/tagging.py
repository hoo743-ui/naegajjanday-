"""Derive place tags from what public data does tell us: category, name and price source.

Bulk public data carries no tags, so `purpose_fit` / `preference_fit` were neutral (0.5) for every one
of the ~800k places and a date course looked exactly like a family course. The rules live in
`data/tagging/tag_rules.json` (DATA — edit the file, restart, every place is re-tagged; no DB rows).

Tags that are stored in the DB (review analysis, user feedback, admin input) always win over a
derived weight: derivation only fills the gaps.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import API_ROOT

RULES_PATH = API_ROOT / "data" / "tagging" / "tag_rules.json"


@dataclass(frozen=True, slots=True)
class TagRules:
    by_category: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    by_name: tuple[tuple[tuple[str, ...], Mapping[str, float]], ...] = ()
    chain_words: tuple[str, ...] = ()
    chain_tag: str = "체인점"
    measured_roles: frozenset[str] = frozenset()
    measured_tags: Mapping[str, float] = field(default_factory=dict)
    hidden: frozenset[str] = frozenset()
    unlisted_ends: tuple[str, ...] = ()
    unlisted_except: tuple[str, ...] = ()
    strip_prefix: tuple[str, ...] = ()
    legal_forms: tuple[str, ...] = ()
    listed_photo_host: str = ""
    listed_tags: Mapping[str, float] = field(default_factory=dict)
    quality_tags: frozenset[str] = frozenset()  # an official body vouches for the place

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> TagRules:
        chains = data.get("chains", {})
        measured = data.get("measured_price", {})
        return cls(
            by_category={k: dict(v) for k, v in data.get("by_category", {}).items()},
            by_name=tuple(
                (tuple(_compact(w) for w in rule["contains"]), dict(rule["tags"]))
                for rule in data.get("by_name", [])
            ),
            chain_words=tuple(_compact(w) for w in chains.get("contains", [])),
            chain_tag=str(chains.get("tag", "체인점")),
            measured_roles=frozenset(measured.get("roles", [])),
            measured_tags=dict(measured.get("tags", {})),
            hidden=frozenset(data.get("hidden_tags", [])),
            unlisted_ends=tuple(_compact(w) for w in data.get("unlisted_names", {}).get("ends_with", [])),
            unlisted_except=tuple(_compact(w) for w in data.get("unlisted_names", {}).get("except", [])),
            listed_photo_host=str(data.get("listed_by_kto", {}).get("photo_host", "")),
            listed_tags=dict(data.get("listed_by_kto", {}).get("tags", {})),
            quality_tags=frozenset(data.get("quality_tags", {}).get("names", [])),
            strip_prefix=tuple(w.upper() for w in data.get("unlisted_names", {}).get("strip_prefix", [])),
            legal_forms=tuple(data.get("unlisted_names", {}).get("legal_forms", [])),
        )

    def derive(
        self,
        *,
        category_code: str,
        name: str,
        course_role: str,
        has_measured_price: bool,
        photo_url: str | None = None,
    ) -> dict[str, float]:
        tags: dict[str, float] = {}

        def put(found: Mapping[str, float]) -> None:
            for tag, weight in found.items():
                tags[tag] = max(tags.get(tag, 0.0), float(weight))

        # general → specific, so "cafe.view" sharpens what "cafe" said
        parts = category_code.split(".")
        for depth in range(1, len(parts) + 1):
            put(self.by_category.get(".".join(parts[:depth]), {}))
        compact = _compact(name)
        for words, found in self.by_name:
            if any(word in compact for word in words):
                put(found)
        if any(word in compact for word in self.chain_words):
            tags[self.chain_tag] = 1.0
            # "역전할머니맥주" matched the 할머니 → 로컬맛집 name rule: a nationwide brand is never local
            for local_only in ("로컬맛집", "시그니처메뉴"):
                tags.pop(local_only, None)
        if has_measured_price and course_role in self.measured_roles:
            put(self.measured_tags)
        if self.listed_photo_host and photo_url and self.listed_photo_host in photo_url:
            put(self.listed_tags)
        return tags

    def is_unlisted(self, name: str) -> bool:
        """A registered company name rather than a shop sign ("티에스리테일", "하이푸드"): nobody can
        find it on a map, so it must not become a course stop."""
        compact = _compact(name)
        if not self.unlisted_ends or any(word in compact for word in self.unlisted_except):
            return False
        for end in self.unlisted_ends:
            at = compact.rfind(end)
            if at < MIN_BODY_BEFORE_SUFFIX:  # "푸드득치킨" starts with the word — that is a brand
                continue
            tail = compact[at + len(end) :]
            if not tail or _BRANCH.fullmatch(tail):  # "하이푸드" / "하이푸드 홍대점"
                return True
        return False

    def sign_name(self, name: str) -> str:
        """The name on the sign: "강남에프앤비화덕고깃간 역삼본점" → "화덕고깃간 역삼본점". Left alone when
        what follows the company word is only a branch ("커피컴퍼니 홍대점") or too short to be a name."""
        # a legal form stuck on either end is never part of the sign: "(주)<hotel>" → "<hotel>"
        for form in self.legal_forms:
            bare = name.strip()
            if bare.startswith(form) and len(_compact(bare[len(form) :])) >= MIN_SIGN_LEN:
                name = bare[len(form) :].strip()
            elif bare.endswith(form) and len(_compact(bare[: -len(form)])) >= MIN_SIGN_LEN:
                name = bare[: -len(form)].strip()
        upper = name.upper()
        for word in self.strip_prefix:
            at = upper.find(word)
            if at < MIN_BODY_BEFORE_SUFFIX:
                continue
            rest = name[at + len(word) :].strip()
            if len(_compact(rest)) >= MIN_SIGN_LEN and not _BRANCH.fullmatch(_compact(rest)):
                return rest
        return name

    def visible(self, tags: Mapping[str, float]) -> dict[str, float]:
        return {t: w for t, w in tags.items() if t not in self.hidden}


_BRANCH = re.compile(r"[가-힣A-Z0-9]{1,6}점")
MIN_BODY_BEFORE_SUFFIX = 2
MIN_SIGN_LEN = 3


def _compact(text: str) -> str:
    return text.replace(" ", "").upper()


@lru_cache(maxsize=1)
def get_tag_rules(path: Path = RULES_PATH) -> TagRules:
    if not path.exists():
        return TagRules()
    return TagRules.from_data(json.loads(path.read_text(encoding="utf-8")))


def merge_tags(stored: Mapping[str, float], derived: Mapping[str, float]) -> dict[str, float]:
    """Stored tags win; derived ones only fill what is missing."""
    return {**derived, **stored}
