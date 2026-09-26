"""처음 · 자주 (docs/59 #1) on plain candidates: what a regular is pulled toward, and what stops pulling."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from app.domain.recommendation import familiarity as F
from app.domain.recommendation.scorer import PlaceScorer, ScoreInput
from app.domain.signature import SignatureRules, mark_local
from tests.factories import SUNDAY_6PM, context, place, profile

RULES = replace(F.familiarity_rules().regular, not_independent_tags=frozenset({"체인점", "무인매장"}))
DAY = SUNDAY_6PM.date()


def test_licence_dates_are_read_in_both_spellings_and_nothing_else() -> None:
    assert F.parse_opened_on({"인허가일자": "2025-03-02"}, "인허가일자") == date(2025, 3, 2)
    assert F.parse_opened_on({"licensed_on": "20240102"}, "licensed_on") == date(2024, 1, 2)
    for raw in ({}, {"인허가일자": ""}, {"인허가일자": "2025-13-40"}, {"인허가일자": "어제"}, None):
        assert F.parse_opened_on(raw, "인허가일자") is None


def test_a_regular_is_two_different_days_not_two_rerolls() -> None:
    assert F.infer([]) == F.FIRST
    assert F.infer([date(2026, 9, 1), date(2026, 9, 1), date(2026, 9, 1)]) == F.FIRST
    assert F.infer([date(2026, 9, 1), date(2026, 9, 20)]) == F.REGULAR


def test_newly_opened_is_an_independent_inside_the_window() -> None:
    fresh = place(opened_on=date(2026, 3, 1))
    assert F.newly_opened(fresh, DAY, RULES)
    assert not F.newly_opened(place(opened_on=date(2016, 3, 1)), DAY, RULES)  # ten years old
    assert not F.newly_opened(place(), DAY, RULES)  # no licence record: simply not known to be new
    # a new branch of a chain is not news to a regular
    assert not F.newly_opened(place(opened_on=date(2026, 3, 1), tags={"체인점": 1.0}), DAY, RULES)


def test_lesser_known_leaves_out_the_listed_the_visited_and_the_signature() -> None:
    assert F.lesser_known(place(), RULES)
    assert not F.lesser_known(place(is_curated=True), RULES)
    assert not F.lesser_known(place(popularity=0.4), RULES)
    assert not F.lesser_known(place(local_score=1.0), RULES)
    assert not F.lesser_known(place(tags={"체인점": 1.0}), RULES)
    assert not F.lesser_known(place(tags={"무인매장": 1.0}), RULES)


def test_the_novelty_pull_is_for_regulars_only() -> None:
    fresh, plain, known = place(opened_on=date(2026, 3, 1)), place(), place(is_curated=True)
    first, regular = context(), context(familiarity=F.REGULAR)
    assert F.novelty_pull(fresh, first) == 0.0 and F.novelty_pull(plain, first) == 0.0
    rules = F.familiarity_rules().regular
    assert F.novelty_pull(fresh, regular) == rules.new_pull
    assert F.novelty_pull(plain, regular) == rules.lesser_known_pull
    assert F.novelty_pull(known, regular) == 0.0
    assert rules.new_pull > rules.lesser_known_pull > 0


def test_a_past_place_let_back_in_counts_for_less() -> None:
    known = place()
    regular = context(familiarity=F.REGULAR, been_place_ids={known.id})
    assert F.novelty_pull(known, regular) == -F.familiarity_rules().regular.been_penalty < 0
    assert F.novelty_pull(known, context(been_place_ids={known.id})) == 0.0  # a first visit: no such thing


def test_the_draw_stops_pulling_for_a_regular() -> None:
    rules = SignatureRules(local_pull=0.05, draw_pull=0.12, specialty_roles=frozenset({"MEAL"}))
    for familiarity, want in ((F.FIRST, 0.12), (F.REGULAR, F.familiarity_rules().regular.draw_pull)):
        shop = place(name="원조닭갈비")
        ctx = context(local_words=("닭갈비",), draw_words=frozenset({"닭갈비"}), familiarity=familiarity)
        mark_local([shop], ctx, rules)
        assert shop.local_score == 1.0  # still what the town is known for (the page may say so)
        assert shop.local_pull == want


def test_a_regular_counts_the_well_known_for_less() -> None:
    listed = place(is_curated=True, popularity=0.9)
    x = ScoreInput(listed, 20000, 0.5, 100.0, datetime(2026, 9, 20, 18, 0), 60)
    first = PlaceScorer(profile(), context()).features(x)["curated"]
    regular = PlaceScorer(profile(), context(familiarity=F.REGULAR)).features(x)["curated"]
    assert regular == first * F.familiarity_rules().regular.known_scale < first


def test_opening_dates_land_on_places_only() -> None:
    a, b = place(), place(is_event=True)
    F.mark_opened([a, b], {a.id: date(2025, 1, 1), b.id: date(2025, 1, 1)})
    assert a.opened_on == date(2025, 1, 1) and b.opened_on is None
