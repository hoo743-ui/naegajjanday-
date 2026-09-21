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
