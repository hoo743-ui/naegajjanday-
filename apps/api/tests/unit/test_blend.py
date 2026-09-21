"""Several purposes for one meeting: weights and likes are averaged, a dislike or a veto is not outvoted."""

from __future__ import annotations

from app.domain.models import FEATURE_KEYS, ScoringProfile, Slot
from app.domain.recommendation.blend import (
    blend_affinity,
    blend_profiles,
    vetoed_roles,
    without_roles,
)
from tests.factories import template


def _profile(code: str, **weights: float) -> ScoringProfile:
    return ScoringProfile(purpose_code=code, version=1, weights=weights)


def test_weights_are_the_mean_of_the_normalized_profiles() -> None:
    blended = blend_profiles([_profile("a", budget=1.0), _profile("b", budget=1.0, distance=1.0)])
    assert blended.purpose_code == "a+b"
    assert abs(blended.weights["budget"] - 0.75) < 1e-9
    assert abs(blended.weights["distance"] - 0.25) < 1e-9
    assert abs(sum(blended.weights[k] for k in FEATURE_KEYS) - 1.0) < 1e-9


def test_a_single_purpose_is_left_exactly_as_it_was() -> None:
    only = _profile("a", budget=0.3, distance=0.7)
    assert blend_profiles([only]) is only
    assert blend_affinity([{"quiet": 0.4}]) == {"quiet": 0.4}


def test_likes_are_averaged_but_a_dislike_is_not_outvoted() -> None:
    blended = blend_affinity([{"quiet": 0.6, "loud": 0.8}, {"loud": -0.5}])
    assert abs(blended["quiet"] - 0.3) < 1e-9  # only one of the two cares
    assert blended["loud"] == -0.5  # the purpose that minds it wins


def test_a_veto_from_any_purpose_removes_the_slot_for_everyone() -> None:
    rules = {"veto_roles": {"kids": ["BAR"]}}
    assert vetoed_roles(["night", "kids"], rules) == frozenset({"BAR"})
    assert vetoed_roles(["night"], rules) == frozenset()

    evening = template(Slot(1, "MEAL", 0.5), Slot(2, "BAR", 0.5))
    only_bar = template(Slot(1, "BAR", 1.0), tid=2)
    kept = without_roles([evening, only_bar], frozenset({"BAR"}))
    assert [[s.course_role for s in t.slots] for t in kept] == [["MEAL"]]  # an emptied template is dropped
    assert without_roles([evening], frozenset()) == [evening]
