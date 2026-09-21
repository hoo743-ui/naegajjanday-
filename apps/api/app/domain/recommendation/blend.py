"""One meeting, several purposes ("a date, and we are also showing a friend around").

The first purpose gives the day its shape (templates); every chosen purpose has a say in what is
picked: the scoring weights are averaged, the tag likes are averaged, and any purpose's dislike or
veto holds for the whole course. A veto is the strong part: if one of the purposes rules a kind of
stop out (no bar on a family outing), it is out, whoever else is coming.

Rules that are opinions rather than arithmetic (which purpose vetoes which role, how many purposes
may be combined) live in `data/recommendation/purpose_blend.json`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import FEATURE_KEYS, ScoringProfile, Template

RULES_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "purpose_blend.json"


@lru_cache(maxsize=1)
def blend_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"max_purposes": 3, "veto_roles": {}}
    return dict(json.loads(path.read_text(encoding="utf-8")))


def blend_profiles(profiles: Sequence[ScoringProfile]) -> ScoringProfile:
    """Mean of the normalized weights. Search parameters (beam width, styles, …) stay the first one's."""
    first = profiles[0]
    if len(profiles) == 1:
        return first
    normalized = [p.normalized_weights() for p in profiles]
    weights = {k: sum(w[k] for w in normalized) / len(normalized) for k in FEATURE_KEYS}
    code = "+".join(p.purpose_code for p in profiles)
    return replace(first, purpose_code=code, weights=weights)


def blend_affinity(affinities: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Likes are averaged over everyone (a tag only one purpose cares about counts for less); a dislike
    is not outvoted: the most negative value stands."""
    if len(affinities) == 1:
        return dict(affinities[0])
    out: dict[str, float] = {}
    for tag in {t for a in affinities for t in a}:
        values = [float(a.get(tag, 0.0)) for a in affinities]
        out[tag] = min(values) if min(values) < 0 else sum(values) / len(values)
    return out


def vetoed_roles(purpose_codes: Sequence[str], rules: Mapping[str, Any] | None = None) -> frozenset[str]:
    veto: Mapping[str, Sequence[str]] = (rules or blend_rules()).get("veto_roles") or {}
    return frozenset(role for code in purpose_codes for role in veto.get(code, ()))


def without_roles(templates: Sequence[Template], roles: frozenset[str]) -> list[Template]:
    """Templates with the vetoed slots taken out. The remaining shares are renormalized by `allocate`,
    so nothing else has to change. A template left with nothing is dropped."""
    if not roles:
        return list(templates)
    kept: list[Template] = []
    for template in templates:
        slots = tuple(s for s in template.slots if s.course_role not in roles)
        if slots:
            kept.append(replace(template, slots=slots))
    return kept
