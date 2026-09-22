"""Preference interpretation (docs/30): few answers in, engine knobs out, conflicts read softly."""

from __future__ import annotations

from app.domain.models import Slot
from app.domain.recommendation import day_score as D
from app.domain.recommendation.preference import interpret, reweight_templates
from tests.factories import template


def test_nothing_chosen_is_a_plain_balanced_day() -> None:
    got = interpret()
    assert got.slot_scale == 1.0 and got.move_style == "balanced" and not got.affinity_add
    assert got.summary[0]["text"] == "짠이가 알아서 균형 있게"


def test_relaxed_means_fewer_longer_stops_and_less_walking() -> None:
    got = interpret(pace=["relaxed"])
    assert got.slot_scale > 1.0 and got.comfort_scale < 1.0


def test_relaxed_and_packed_keep_the_count_but_weigh_standouts() -> None:
    got = interpret(pace=["relaxed", "packed"])
    assert got.slot_scale == 1.0
    assert got.day_score["destination"] > D.DEFAULT_DAY_WEIGHTS["destination"]
    assert got.notes


def test_at_most_two_paces() -> None:
    assert len(interpret(pace=["relaxed", "packed", "foodie"]).pace) == 2


def test_special_is_the_fun_style_with_something_to_do() -> None:
    got = interpret(pace=["special"])
    assert got.style == "fun" and got.structure_fill[0] == "ACTIVITY"


def test_a_wish_becomes_tag_affinities() -> None:
    got = interpret(wishes=["night", "romantic"])
    assert got.affinity_add["야경명소"] > 0 and got.affinity_add["로맨틱"] > 0
    assert [line["text"] for line in got.summary if line["kind"] == "wish"] == [
        "야경 포함",
        "로맨틱한 분위기",
    ]


def test_an_explicit_avoid_beats_an_implied_like() -> None:
    got = interpret(wishes=["romantic"], disliked_tags=["감성적인"])
    assert got.affinity_add["감성적인"] == 0.0


def test_exhibition_asks_for_culture_first() -> None:
    assert interpret(pace=["special"], wishes=["exhibition"]).structure_fill[0] == "CULTURE"


def test_value_spends_less_on_purpose() -> None:
    got = interpret(wishes=["value"], budget_total=80000, party_size=2)
    assert got.params["budget_target_util"] < 0.85
    assert got.summary[-1]["text"] == "80,000원 아껴서 · 1인 40,000원"


def test_foodie_gives_the_meal_more_of_the_budget() -> None:
    t = template(Slot(1, "MEAL", 0.5), Slot(2, "CAFE", 0.3), Slot(3, "ATTRACTION", 0.2))
    (out,) = reweight_templates([t], interpret(pace=["foodie"]).role_share)
    shares = {s.course_role: s.budget_share for s in out.slots}
    assert shares["MEAL"] > 0.5 and abs(sum(shares.values()) - 1.0) < 1e-3


def test_structure_follows_the_asked_fill_order() -> None:
    t = template(Slot(1, "CAFE", 0.3), Slot(2, "DESSERT", 0.3))
    alt = D.structure_alternative(t, ("ACTIVITY",))
    assert alt is not None and alt.slots[1].course_role == "ACTIVITY"
