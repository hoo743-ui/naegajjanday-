from __future__ import annotations

import pytest

from app.domain.models import Slot
from app.domain.recommendation.candidates import FilterContext, rejection_reason
from app.domain.recommendation.style import (
    assign_buzz,
    resolve_style,
    styled_affinity,
    styled_avoidance,
    styled_profile,
    styled_templates,
)
from tests.factories import DATE_EVENING, SUNDAY_6PM, context, place, profile, template


def test_unknown_style_falls_back_to_efficient_and_changes_nothing() -> None:
    base = profile()
    name, style = resolve_style(base, "whatever")
    assert name == "efficient" and styled_profile(base, style) is base
    assert styled_templates([DATE_EVENING], style) == [DATE_EVENING]


def test_fun_walks_further_and_rewards_a_busy_street() -> None:
    base = profile()
    _, style = resolve_style(base, "fun")
    fun, plain = styled_profile(base, style).normalized_weights(), base.normalized_weights()
    assert fun["distance"] < plain["distance"]
    assert fun["buzz"] > 0 and plain["buzz"] == 0


def test_fun_turns_the_park_stroll_into_an_activity_once() -> None:
    _, style = resolve_style(profile(), "fun")
    [swapped] = styled_templates([DATE_EVENING], style)
    assert [s.course_role for s in swapped.slots] == ["MEAL", "CAFE", "ACTIVITY", "BAR"]
    # 놀거리 예산은 식사에서 가져온다 — 술집 비중은 그대로여야 저녁의 마지막 코스가 살아남는다
    before = {s.course_role: s.budget_share for s in DATE_EVENING.slots}
    after = {s.course_role: s.budget_share for s in swapped.slots}
    assert after["BAR"] == before["BAR"] and after["CAFE"] == before["CAFE"]
    assert after["MEAL"] == pytest.approx(before["MEAL"] - (0.14 - before["ATTRACTION"]))
    # a template that already has an ACTIVITY keeps its stroll — no second activity slot
    has_activity = template(Slot(1, "MEAL", 0.6), Slot(2, "ATTRACTION", 0.05), Slot(3, "ACTIVITY", 0.35))
    [kept] = styled_templates([has_activity], style)
    assert [s.course_role for s in kept.slots] == ["MEAL", "ATTRACTION", "ACTIVITY"]


def test_fun_penalizes_chains_within_bounds() -> None:
    _, style = resolve_style(profile(), "fun")
    out = styled_affinity({"체인점": -0.6, "로맨틱": 0.9}, style)
    assert out["체인점"] == -1.0 and out["로맨틱"] == 0.9 and out["체험형"] == pytest.approx(0.6)


def test_profile_params_can_override_a_style() -> None:
    custom = profile(styles={"fun": {"weight_add": {"buzz": 0.5}}})
    _, style = resolve_style(custom, "fun")
    # 덮어쓴 항목만 바뀌고 나머지 기본값(놀거리 교체·체인 회피)은 그대로 — 목적마다 전부 다시 쓰지 않아도 된다
    assert style["weight_add"] == {"buzz": 0.5} and "swap_roles" in style and "avoid_tags" in style
    _, plain = resolve_style(profile(styles={"efficient": {"avoid_tags": {"체인점": ["CAFE"]}}}), None)
    assert plain == {"avoid_tags": {"체인점": ["CAFE"]}}


def test_buzz_is_high_in_a_packed_street_and_zero_alone() -> None:
    street = [place("MEAL", "food.korean", 9000, dlat=0.0001 * i) for i in range(8)]  # ≈ 11 m apart
    loner = place("MEAL", "food.korean", 9000, dlat=0.02)  # ≈ 2.2 km away
    assign_buzz([*street, loner])
    assert all(p.buzz == 1.0 for p in street) and loner.buzz == 0.0


def test_fun_bans_chain_cafes_but_keeps_chain_pubs() -> None:
    _, style = resolve_style(profile(), "fun")
    ctx = context(budget_total=200000)
    ctx.avoid_tags_by_role = styled_avoidance(style)
    params = profile().params
    cafe = place("CAFE", "cafe.coffee", 4500, tags={"체인점": 1.0})
    pub = place("BAR", "bar.pub", 16000, tags={"체인점": 1.0})
    assert (
        rejection_reason(cafe, FilterContext.build(ctx, "CAFE", 10000, SUNDAY_6PM), params) == "excluded_tag"
    )
    assert rejection_reason(pub, FilterContext.build(ctx, "BAR", 30000, SUNDAY_6PM), params) != "excluded_tag"


def test_asking_for_a_drink_puts_the_bar_in_every_template() -> None:
    from app.domain.recommendation.style import with_role

    extra = {"role": "BAR", "share": 0.25, "earliest_start_min": 1020, "latest_start_min": 1410}
    lunch = template(Slot(1, "MEAL", 0.6), Slot(2, "CAFE", 0.4), time_band="lunch")
    evening = template(Slot(1, "MEAL", 0.5), Slot(2, "BAR", 0.5, is_optional=True), tid=2)

    added, kept = with_role([lunch, evening], extra)

    assert [s.course_role for s in added.slots] == ["MEAL", "CAFE", "BAR"]
    assert abs(sum(s.budget_share for s in added.slots) - 1.0) < 1e-9  # the others made room
    assert added.slots[-1].earliest_start_min == 1020  # never a bar stop at lunchtime
    assert [s.is_optional for s in kept.slots] == [False, False]  # "if it fits" became "for certain"
    assert kept.slots[1].budget_share == 0.5  # a template that planned for it keeps its own share


def test_an_opt_in_category_stays_out_until_it_is_asked_for() -> None:
    from app.domain.recommendation.candidates import FilterContext, hard_filter
    from app.domain.recommendation.style import opt_in_categories, wanted_pools

    assert "activity.stadium" in opt_in_categories()  # no schedule data: never guessed into a course
    park = place("ACTIVITY", "activity.stadium", 15000)
    arcade = place("ACTIVITY", "activity.arcade", 8000)
    params = profile().params

    quiet = context(blocked_categories=opt_in_categories())
    fc = FilterContext.build(quiet, "ACTIVITY", 30000, SUNDAY_6PM)
    assert hard_filter([park, arcade], fc, params) == [arcade]

    asked = context(wanted_categories=("activity.stadium",))
    fc = FilterContext.build(asked, "ACTIVITY", 30000, SUNDAY_6PM)
    pools = wanted_pools(
        {1: [place("MEAL")], 2: hard_filter([park, arcade], fc, params)}, asked.wanted_categories
    )
    assert pools[2] == [park]  # the slot that can hold it offers nothing else
    assert len(pools[1]) == 1  # other slots are untouched
