"""What a neighbourhood is known for, read off the shop signs.

No list of "famous things" exists as open data, and hand-writing one per region is exactly the
hard-coding this project forbids. But the signs themselves carry it: a word that is rare across the
country and thick on the ground here (and still used elsewhere, so it is a thing and not a street
name) is what people come to this neighbourhood to eat. Sights are ranked the same way: a sight that
nearby shops name themselves after is the one the neighbourhood is organised around.

Pure functions only; `services.signature_service` feeds them rows and stores the result.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.models import PlaceCandidate, RequestContext

RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "signature" / "signature_rules.json"
_WORD_RUN = re.compile("[가-힣]+")  # runs of Hangul syllables


@dataclass(frozen=True, slots=True)
class SignatureRules:
    gram_lengths: tuple[int, ...] = (2, 3, 4, 5, 6)
    specialty_roles: frozenset[str] = frozenset()
    sight_roles: frozenset[str] = frozenset()
    levels: tuple[int, ...] = (2, 3)
    max_radius_m: int = 3000
    min_local: int = 4
    min_outside: int = 15
    min_lift: float = 5.0
    min_toponym_hits: int = 3
    longer_keeps_ratio: float = 0.8
    max_specialties: int = 6
    max_sights: int = 5
    sight_key_len: int = 4
    station_radius_factor: float = 2.0
    min_leading_ratio: float = 0.0  # off: signs are head-final, the dish closes the name
    short_word_len: int = 2
    short_word_min_count: int = 30
    short_word_min_lift: float = 30.0
    drop_suffixes: tuple[str, ...] = ()
    admin_suffixes: tuple[str, ...] = ()
    stopwords: frozenset[str] = frozenset()
    tag: str = ""
    landmark_score: float = 1.0
    specialty_score: float = 1.0
    listed_score: float = 0.7
    focus_bonus: float = 0.35
    auto_focus_min_strength: float = 30.0
    auto_focus_min_pool: int = 2
    focus_avoid_categories: tuple[str, ...] = ()

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> SignatureRules:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for key in ("gram_lengths", "levels", "drop_suffixes", "admin_suffixes", "focus_avoid_categories"):
            if key in known:
                known[key] = tuple(known[key])
        for key in ("specialty_roles", "sight_roles", "stopwords"):
            if key in known:
                known[key] = frozenset(known[key])
        return cls(**known)


@lru_cache(maxsize=1)
def get_signature_rules(path: Path = RULES_PATH) -> SignatureRules:
    if not path.exists():
        return SignatureRules()
    return SignatureRules.from_data(json.loads(path.read_text(encoding="utf-8")))


def grams(text: str, lengths: Sequence[int]) -> set[str]:
    """Every syllable n-gram of the text, once per text (document frequency, not term frequency)."""
    out: set[str] = set()
    for run in _WORD_RUN.findall(text or ""):
        for n in lengths:
            for i in range(len(run) - n + 1):
                out.add(run[i : i + n])
    return out


def leading_grams(text: str, lengths: Sequence[int]) -> set[str]:
    """The n-grams that open a run of syllables: where a word can stand, a fragment hardly ever does."""
    return {run[:n] for run in _WORD_RUN.findall(text or "") for n in lengths if len(run) >= n}


def place_words(names: Iterable[str], admin_suffixes: Sequence[str], min_len: int = 2) -> tuple[str, ...]:
    """The bare names of a region and its ancestors, administrative endings removed, longest first."""
    out: set[str] = set()
    for name in names:
        for run in _WORD_RUN.findall(name or ""):
            bare = next(
                (run[: -len(sfx)] for sfx in admin_suffixes if run.endswith(sfx) and len(run) > len(sfx)), run
            )
            out.update(w for w in (run, bare) if len(w) >= min_len)
    return tuple(sorted(out, key=len, reverse=True))


def without(text: str, words: Sequence[str]) -> str:
    """The sign with the town's own name taken out, so "<town><dish>" counts as the dish."""
    for word in words:
        text = text.replace(word, " ")
    return text


def compact(text: str) -> str:
    return "".join(_WORD_RUN.findall(text or ""))


def count_grams(names: Iterable[str], lengths: Sequence[int], only: set[str] | None = None) -> Counter[str]:
    out: Counter[str] = Counter()
    for name in names:
        found = grams(name, lengths)
        out.update(found if only is None else found & only)
    return out


@dataclass(frozen=True, slots=True)
class Specialty:
    word: str
    count: int  # shops here whose sign carries the word
    lift: float  # how many times denser than the country as a whole

    @property
    def strength(self) -> float:
        """Evidence that this is what the place is known for: many signs, and far denser than elsewhere."""
        return self.count * math.log(max(self.lift, 1.0))


@dataclass(frozen=True, slots=True)
class Sight:
    place_id: int
    name: str
    mentions: int  # nearby shops named after it


@dataclass(frozen=True, slots=True)
class Signature:
    specialties: tuple[Specialty, ...] = ()
    sights: tuple[Sight, ...] = ()
    shops: int = 0

    def strong(self, floor: float) -> Signature:
        """Only the specialties with enough evidence to be said out loud and to steer a course. A weak
        one is as likely a slice of a brand name as a dish, and a busy district has plenty of those."""
        kept = tuple(s for s in self.specialties if s.strength >= floor)
        return Signature(specialties=kept, sights=self.sights, shops=self.shops)

    def to_payload(self) -> dict[str, Any]:
        return {
            "shops": self.shops,
            "specialties": [{"word": s.word, "count": s.count, "lift": s.lift} for s in self.specialties],
            "sights": [{"place_id": s.place_id, "name": s.name, "mentions": s.mentions} for s in self.sights],
        }

    @classmethod
    def from_payload(cls, data: Mapping[str, Any] | None) -> Signature:
        if not data:
            return cls()
        return cls(
            specialties=tuple(
                Specialty(str(s["word"]), int(s["count"]), float(s["lift"]))
                for s in data.get("specialties", [])
            ),
            sights=tuple(
                Sight(int(s["place_id"]), str(s["name"]), int(s.get("mentions", 0)))
                for s in data.get("sights", [])
            ),
            shops=int(data.get("shops", 0)),
        )


def pick_specialties(
    local: Mapping[str, int],
    local_shops: int,
    national: Mapping[str, int],
    national_shops: int,
    toponyms: Iterable[str],
    rules: SignatureRules,
    national_leading: Mapping[str, int] | None = None,
) -> tuple[Specialty, ...]:
    """Words thick on the ground here, rare across the country, and still in use elsewhere.

    `min_outside` is what separates a thing from a place: a street or station name is as dense as a
    local dish but hardly occurs outside the neighbourhood, while the dish is sold under that word in
    other cities too.
    """
    if local_shops <= 0 or national_shops <= 0:
        return ()
    places = set(toponyms)
    # A cut across a word boundary ("brand + district") always drags the same neighbour along: if one
    # more syllable keeps nearly the whole count, the shorter string was never a word of its own.
    longer: dict[str, int] = {}
    for word, count in local.items():
        for part in (word[1:], word[:-1]):
            if len(part) >= 2 and count > longer.get(part, 0):
                longer[part] = count
    scored: list[tuple[float, Specialty]] = []
    for word, count in local.items():
        if count < rules.min_local or word in places or word in rules.stopwords:
            continue
        if longer.get(word, 0) >= rules.longer_keeps_ratio * count and len(word) < max(rules.gram_lengths):
            continue
        if any(word.endswith(suffix) for suffix in rules.drop_suffixes):
            continue
        everywhere = max(national.get(word, 0), count)
        if everywhere - count < rules.min_outside:
            continue
        lift = (count / local_shops) / (everywhere / national_shops)
        if lift < rules.min_lift:
            continue
        # two syllables are as often a slice of a longer word as a word: ask for much stronger evidence
        if (
            len(word) <= rules.short_word_len
            and count < rules.short_word_min_count
            and lift < rules.short_word_min_lift
        ):
            continue
        if (
            national_leading is not None
            and national_leading.get(word, 0) < rules.min_leading_ratio * everywhere
        ):
            continue
        scored.append((count * math.log(lift), Specialty(word, count, round(lift, 1))))
    scored.sort(key=lambda t: (-t[0], t[1].word))

    kept: list[Specialty] = []
    for _, found in scored:
        clash = next((k for k in kept if found.word in k.word or k.word in found.word), None)
        if clash is None:
            kept.append(found)
        elif len(found.word) > len(clash.word) and found.count >= rules.longer_keeps_ratio * clash.count:
            kept[kept.index(clash)] = found  # the fragment was standing in for the whole word
    return tuple(kept[: rules.max_specialties])


def rank_sights(
    sights: Sequence[tuple[int, str, bool]],
    shop_names: Sequence[str],
    rules: SignatureRules,
    region_words: Iterable[str] = (),
) -> tuple[Sight, ...]:
    """`sights` are (place_id, name, has_photo). Ranked by how many shops borrow the name, then photo.

    The name is matched by its first word that is not the region itself: every branch in town carries
    the city's name, which says nothing about the sight."""
    shops = [compact(name) for name in shop_names]
    region = set(region_words)
    ranked: list[tuple[int, bool, Sight]] = []
    seen: list[str] = []
    for place_id, name, has_photo in sights:
        key = compact(name)
        if len(key) < 3 or any(key in other or other in key for other in seen):
            continue  # the same sight listed twice under a longer/shorter name
        seen.append(key)
        words = [w for w in (compact(part) for part in name.split()) if len(w) >= 2 and w not in region]
        needle = (words[0] if words else key)[: rules.sight_key_len]
        mentions = sum(1 for shop in shops if needle in shop) if needle not in region else 0
        ranked.append((mentions, has_photo, Sight(place_id, name, mentions)))
    ranked.sort(key=lambda t: (-t[0], not t[1], t[2].name))
    return tuple(s for _, _, s in ranked[: rules.max_sights])


def mark_local(candidates: Iterable[PlaceCandidate], ctx: RequestContext, rules: SignatureRules) -> None:
    """Flags what the neighbourhood is known for: shops whose sign carries a specialty word, and the
    sights the neighbourhood is organised around. Feeds the `curated` feature and the visible tag."""
    if not ctx.local_words and not ctx.landmark_ids:
        return
    for cand in candidates:
        if cand.is_event:
            continue
        if cand.course_role in rules.specialty_roles:
            flat = compact(cand.name)
            word = next((w for w in ctx.local_words if w in flat), None)
            if word is not None:
                cand.local_score, cand.local_word = rules.specialty_score, word
        elif cand.id in ctx.landmark_ids:
            cand.local_score = rules.landmark_score
        if cand.local_score > 0 and rules.tag:
            cand.tags = {**cand.tags, rules.tag: 1.0}


def focus_pools(
    pools: Mapping[int, list[PlaceCandidate]],
    ctx: RequestContext,
    rules: SignatureRules,
    unfiltered: Iterable[PlaceCandidate] = (),
) -> dict[int, list[PlaceCandidate]]:
    """One stop of the course is given to what the neighbourhood is known for.

    The user's pick (`ctx.focus_request`) comes first. Otherwise, or when the pick does not fit the
    budget of any slot, the strongest specialty that at least `auto_focus_min_pool` affordable shops
    can serve is chosen, so a course in a crab town has crab in it without being asked. The first slot
    that can serve it serves nothing else; every other slot is untouched, and with no clear specialty
    the pools come back as they were. `ctx.focus` records the word that was applied; when the pick
    itself could not be served, `ctx.focus_from_price` says what it costs so the page can explain.
    """
    out = dict(pools)
    ctx.focus = None
    wanted = [(ctx.focus_request, 1)] if ctx.focus_request else []
    wanted += [(w, rules.auto_focus_min_pool) for w in ctx.auto_focus_words if w != ctx.focus_request]
    for word, need in wanted:
        for position in sorted(out):
            matching = [c for c in out[position] if not c.is_event and word in compact(c.name)]
            # a sit-down place: "<specialty> instant noodles" is not the dish
            if rules.focus_avoid_categories:
                matching = [
                    c for c in matching if not c.category_code.startswith(rules.focus_avoid_categories)
                ]
            if len(matching) >= need:
                out[position] = matching
                ctx.focus = word
                return out
        if word == ctx.focus_request:
            prices = [
                c.price_per_person
                for c in unfiltered
                if c.price_per_person
                and not c.is_event
                and word in compact(c.name)
                and not (
                    rules.focus_avoid_categories and c.category_code.startswith(rules.focus_avoid_categories)
                )
            ]
            ctx.focus_from_price = min(prices, default=None)
    return out
