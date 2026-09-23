"""Preference interpretation layer (docs/30): few words from the user, rich knobs for the engine.

The wizard asks three things — what kind of day (pace), how far is fine (move style), what must be in it
(a few quick wishes) — and, only if the user opens "더 자세히", the detailed tags. This module turns those
answers into the knobs the engine already has, instead of handing raw chips to it:

    pace ("여유롭게", "알차게", "맛있는 거 중심", "특별한 경험")
        → stop count (minutes a stop takes), stay length, travel tolerance, style, weights, meal share
    move style (local · balanced · explorer)
        → comfortable leg and reach rings (day_score.MOVE_STYLES) — a preference, never a distance filter
    wishes (야경 · 산책 · 전시 · 가성비 · 로맨틱 · 조용하게 · 실내 위주 · 사진 · 무료)
        → tag affinities, structure hints, budget posture, pulls toward a kind of place (photo, free, quiet),
          and for "실내 위주" the rainy-day condition itself (`WISH_CONDITIONS`)
    detailed tags → liked / disliked tags, as before

Three layers are kept apart (docs/30 §13):
    HARD        the request's own limits: date, party, budget ceiling, time window, "술 한잔 포함" …
                (never touched here; the engine enforces them)
    PREFERENCE  wishes and detailed tags — soft weights; an explicit "피할래요" beats an implied like
    STYLE       the pace — the shape of the day

Conflicting answers never fail: "여유롭게 + 알차게" becomes "not more stops, but denser ones"; a tag both
implied and avoided is dropped from the implied side. Everything is a soft weight, so the purpose, the
budget and the time still decide first.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.domain.models import Template

PACES = ("relaxed", "packed", "foodie", "special")
MOVE_STYLES = ("local", "balanced", "explorer")
WISHES = ("night", "walk", "exhibition", "value", "romantic", "quiet", "indoor", "photo", "free")

PACE_LABEL = {
    "relaxed": "여유로운 하루",
    "packed": "알찬 하루",
    "foodie": "맛있는 거 중심",
    "special": "특별한 경험",
}
MOVE_LABEL = {"local": "가까운 곳 위주", "balanced": "적당히 이동", "explorer": "좋은 곳이면 조금 멀리도"}
WISH_LABEL = {
    "night": "야경 포함",
    "walk": "산책 넣기",
    "exhibition": "전시 · 공연 넣기",
    "value": "가성비 있게",
    "romantic": "로맨틱한 분위기",
    "quiet": "조용한 곳 위주",
    "indoor": "실내 위주",
    "photo": "사진이 있는 곳 위주",
    "free": "무료로 들를 곳 더",
}

# what each wish means in the tag vocabulary the places already carry (tag_rules.json)
WISH_TAGS: dict[str, dict[str, float]] = {
    "night": {"야경명소": 0.6, "뷰맛집": 0.2},
    "walk": {"산책하기좋은": 0.6, "야외": 0.1},
    "exhibition": {"전시공연": 0.6},
    "value": {"가성비": 0.5, "착한가격업소": 0.4},
    "romantic": {"로맨틱": 0.5, "감성적인": 0.3, "활기찬": -0.1},
    "quiet": {"조용한": 0.5, "아늑한": 0.3, "감성적인": 0.1, "활기찬": -0.6},
    "indoor": {},  # the rainy-day condition does it (WISH_CONDITIONS)
    "photo": {},  # a pull toward places with their own photo (WISH_PULL)
    "free": {"산책하기좋은": 0.2},
}
# wishes about the kind of place rather than a tag: added to the place score (scorer.trait_pull)
WISH_PULL: dict[str, dict[str, float]] = {
    "quiet": {"buzz": -0.08},
    "photo": {"photo": 0.1},
    "free": {"free": 0.12},
}
# "실내 위주" is what a rainy day already is: the same condition (data/recommendation/conditions.json)
WISH_CONDITIONS: dict[str, str] = {"indoor": "rain"}
# "조용하게": no pub in the day and no karaoke room, unless the user asked for a drink by name
WISH_AVOID_ROLES: dict[str, tuple[str, ...]] = {"quiet": ("BAR",)}
WISH_BLOCKED_CATEGORIES: dict[str, tuple[str, ...]] = {"quiet": ("activity.karaoke",)}
PACE_TAGS: dict[str, dict[str, float]] = {
    "relaxed": {"조용한": 0.2, "아늑한": 0.2},
    "packed": {},
    "foodie": {"로컬맛집": 0.4, "시그니처메뉴": 0.4, "디저트맛집": 0.2},
    "special": {"체험형": 0.4, "포토존": 0.2},
}
# minutes one stop takes out of the meeting window, relative to the engine's nominal slot
SLOT_SCALE = {"relaxed": 1.25, "packed": 0.85}
MEAL_SHARE_FOODIE = 1.25
EXPLICIT_WIN = 0.0  # an implied like of a tag the user said to avoid is dropped entirely


@dataclass(slots=True)
class Interpreted:
    """What the engine is given. `summary` is what the user is told, in words, before anything is built."""

    pace: tuple[str, ...] = ()
    move_style: str = "balanced"
    wishes: tuple[str, ...] = ()
    style: str = "efficient"  # the existing style knob (efficient | fun)
    slot_scale: float = 1.0
    comfort_scale: float = 1.0
    weight_mult: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    day_score: dict[str, float] = field(default_factory=dict)
    affinity_add: dict[str, float] = field(default_factory=dict)
    role_share: dict[str, float] = field(default_factory=dict)
    structure_fill: tuple[str, ...] = ()  # which kind a repeated slot should become, first choice first
    trait_pull: dict[str, float] = field(default_factory=dict)  # see WISH_PULL
    liked_tags: list[str] = field(default_factory=list)
    disliked_tags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # how conflicts were read (internal)
    summary: list[dict[str, str]] = field(default_factory=list)

    def layers(self) -> dict[str, list[str]]:
        return {
            "style": [PACE_LABEL[p] for p in self.pace],
            "preference": [WISH_LABEL[w] for w in self.wishes] + self.liked_tags,
            "avoid": list(self.disliked_tags),
        }

    @property
    def conditions(self) -> tuple[str, ...]:
        """Day conditions a wish stands for ("실내 위주" = the rainy-day plan)."""
        return tuple(dict.fromkeys(WISH_CONDITIONS[w] for w in self.wishes if w in WISH_CONDITIONS))

    @property
    def avoid_roles(self) -> frozenset[str]:
        return frozenset(r for w in self.wishes for r in WISH_AVOID_ROLES.get(w, ()))

    @property
    def blocked_categories(self) -> frozenset[str]:
        return frozenset(c for w in self.wishes for c in WISH_BLOCKED_CATEGORIES.get(w, ()))

    def as_style(self) -> dict[str, Any]:
        """In the shape `style.styled_profile` / `styled_affinity` already understand."""
        params = dict(self.params)
        if self.comfort_scale != 1.0:
            params["comfort_leg_scale"] = self.comfort_scale
        if self.day_score:
            params["day_score"] = dict(self.day_score)
        return {
            "weight_mult": dict(self.weight_mult),
            "params": params,
            "affinity_add": dict(self.affinity_add),
        }


def _add(target: dict[str, float], found: Mapping[str, float]) -> None:
    for tag, delta in found.items():
        target[tag] = round(max(-1.0, min(1.0, target.get(tag, 0.0) + delta)), 3)


def interpret(
    *,
    pace: Iterable[str] = (),
    move_style: str | None = None,
    wishes: Iterable[str] = (),
    liked_tags: Sequence[str] = (),
    disliked_tags: Sequence[str] = (),
    budget_total: int | None = None,
    party_size: int = 1,
) -> Interpreted:
    chosen = tuple(dict.fromkeys(p for p in pace if p in PACES))[:2]
    wanted = tuple(dict.fromkeys(w for w in wishes if w in WISHES))
    move = move_style if move_style in MOVE_STYLES else "balanced"
    out = Interpreted(pace=chosen, move_style=move, wishes=wanted)
    out.disliked_tags = list(dict.fromkeys(disliked_tags))
    out.liked_tags = [t for t in dict.fromkeys(liked_tags) if t not in out.disliked_tags]

    relaxed, packed = "relaxed" in chosen, "packed" in chosen
    if relaxed and packed:
        # 여유롭게 + 알차게: not more stops, but each of them worth it
        out.notes.append("relaxed+packed: keep the stop count, weigh standout places more")
        out.day_score["destination"] = 0.1
        out.weight_mult["curated"] = 1.3
    elif relaxed:
        out.slot_scale = SLOT_SCALE["relaxed"]
        out.comfort_scale = 0.9  # an unhurried day walks less between stops
    elif packed:
        out.slot_scale = SLOT_SCALE["packed"]
    if "foodie" in chosen:
        out.role_share["MEAL"] = MEAL_SHARE_FOODIE
        out.weight_mult["curated"] = max(out.weight_mult.get("curated", 1.0), 1.2)
    if "special" in chosen:
        out.style = "fun"  # the existing "재미 우선" twist: lively streets, things to do, fewer chains
        out.day_score["destination"] = max(out.day_score.get("destination", 0.06), 0.1)
        out.structure_fill = ("ACTIVITY", "CULTURE")
    for p in chosen:
        _add(out.affinity_add, PACE_TAGS[p])

    for w in wanted:
        _add(out.affinity_add, WISH_TAGS[w])
        for trait, pull in WISH_PULL.get(w, {}).items():
            out.trait_pull[trait] = round(out.trait_pull.get(trait, 0.0) + pull, 3)
    if "exhibition" in wanted:
        out.structure_fill = ("CULTURE", *[r for r in out.structure_fill if r != "CULTURE"])
    if "value" in wanted:
        # spend less of the budget on purpose: the "가성비" variant's posture
        out.params.update({"budget_target_util": 0.7, "utilization_lo": 0.55, "utilization_hi": 0.85})
    if "free" in wanted:
        # more of the day costs nothing: an even lower posture, and a repeated slot becomes a free sight
        out.params.update({"budget_target_util": 0.6, "utilization_lo": 0.4, "utilization_hi": 0.8})
        out.structure_fill = (
            *out.structure_fill,
            *[r for r in ("ATTRACTION",) if r not in out.structure_fill],
        )
    if "quiet" in wanted:
        out.weight_mult["congestion"] = max(out.weight_mult.get("congestion", 1.0), 1.5)
    if relaxed and "활기찬" in out.liked_tags:
        out.notes.append("relaxed+lively: both kept as soft weights")

    # an explicit "피할래요" always beats what a pace or wish implied
    for tag in out.disliked_tags:
        if out.affinity_add.get(tag, 0.0) > 0:
            out.affinity_add[tag] = EXPLICIT_WIN
            out.notes.append(f"'{tag}' avoided explicitly: implied like dropped")

    out.summary = _summary(out, budget_total, party_size)
    return out


def _summary(out: Interpreted, budget_total: int | None, party_size: int) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    if out.pace:
        lines.append(
            {"kind": "pace", "key": out.pace[0], "text": " · ".join(PACE_LABEL[p] for p in out.pace)}
        )
    else:
        lines.append({"kind": "pace", "key": "auto", "text": "짠이가 알아서 균형 있게"})
    lines.append({"kind": "move", "key": out.move_style, "text": MOVE_LABEL[out.move_style]})
    for w in out.wishes:
        lines.append({"kind": "wish", "key": w, "text": WISH_LABEL[w]})
    if out.liked_tags:
        lines.append(
            {"kind": "detail", "key": "liked", "text": f"고른 취향 {len(out.liked_tags)}가지 더 반영"}
        )
    if out.disliked_tags:
        lines.append(
            {"kind": "detail", "key": "avoid", "text": f"피하고 싶은 것 {len(out.disliked_tags)}가지는 빼고"}
        )
    if budget_total:
        each = f" · 1인 {budget_total // max(1, party_size):,}원" if party_size > 1 else ""
        posture = "아껴서" if {"value", "free"} & set(out.wishes) else "안에서 안정적으로"
        lines.append({"kind": "budget", "key": "budget", "text": f"{budget_total:,}원 {posture}{each}"})
    return lines


def reweight_templates(templates: Sequence[Template], role_share: Mapping[str, float]) -> list[Template]:
    """A foodie day gives the meal a larger share of the budget; the other slots give it up evenly."""
    if not role_share:
        return list(templates)
    out = []
    for t in templates:
        raw = [s.budget_share * role_share.get(s.course_role, 1.0) for s in t.slots]
        total = sum(raw) or 1.0
        before = sum(s.budget_share for s in t.slots) or 1.0
        slots = tuple(
            replace(s, budget_share=round(r / total * before, 4)) for s, r in zip(t.slots, raw, strict=True)
        )
        out.append(replace(t, slots=slots))
    return out
