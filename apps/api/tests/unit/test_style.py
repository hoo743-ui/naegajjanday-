from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.models import Slot
from app.domain.recommendation.candidates import FilterContext, never_tags, rejection_reason
from app.domain.recommendation.style import (
    assign_buzz,
    resolve_style,
    styled_affinity,
    styled_avoidance,
    styled_never,
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


def test_a_date_never_ends_at_an_unmanned_cafe() -> None:
    # 2026-09-24: 숭실대 밤 10시 데이트 세 코스가 모두 '틈새24시무인카페'로 끝났다 (밤에 연 카페가 그곳뿐)
    from app.infra.tagging import get_tag_rules

    tags = get_tag_rules().derive(
        category_code="cafe", name="틈새24시무인카페", course_role="CAFE", has_measured_price=False
    )
    assert tags.get("무인매장") == 1.0 and "무인매장" not in get_tag_rules().visible(tags)
    ctx = context(budget_total=60000)
    ctx.never_tags_by_role = styled_never({"never_tags": {"무인매장": ["CAFE", "DESSERT"]}})
    params = profile().params
    unmanned = place("CAFE", "cafe", 6000, tags=tags)
    assert (
        rejection_reason(unmanned, FilterContext.build(ctx, "CAFE", 10000, SUNDAY_6PM), params)
        == "excluded_tag"
    )
    # the style's own avoidance is relaxed when nothing else is left; this one is not
    assert never_tags(ctx, "CAFE") == {"무인매장"} and never_tags(ctx, "BAR") == frozenset()


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


def test_a_film_asked_by_name_gets_a_ticket_sized_share_of_the_fun_slot() -> None:
    from app.domain.recommendation.style import with_role

    extra = {"role": "ACTIVITY", "share": 0.5, "category": "activity.cinema", "min_slot_budget": 10000}
    date = template(Slot(1, "MEAL", 0.6), Slot(2, "CAFE", 0.25), Slot(3, "ACTIVITY", 0.15, is_optional=True))

    (out,) = with_role([date], extra)

    assert out.slots[2].budget_share == 0.5 and not out.slots[2].is_optional
    assert abs(sum(s.budget_share for s in out.slots) - 1.0) < 1e-9
    assert out.slots[0].budget_share > out.slots[1].budget_share  # the others shrink in proportion


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


def test_a_mountain_top_view_is_not_a_night_walk() -> None:
    # 2026-09-25: 강남역 밤 도보 코스가 우면산 소망탑(00:30 도착, 31분 걷기)으로 끝났다 — 차로는 괜찮다
    ctx = context(budget_total=60000)
    ctx.avoid_names = frozenset({"소망탑", "산전망대"})
    params = profile().params
    peak = replace(place("NIGHTVIEW", "nightview", 0), name="우면산 소망탑")
    ridge = replace(place("NIGHTVIEW", "nightview", 0), name="황령산 전망대")
    river = replace(place("NIGHTVIEW", "nightview", 0), name="반포한강공원 달빛무지개분수")
    fc = FilterContext.build(ctx, "NIGHTVIEW", 0, SUNDAY_6PM)
    assert rejection_reason(peak, fc, params) == "avoided_name"
    assert rejection_reason(ridge, fc, params) == "avoided_name"
    assert rejection_reason(river, fc, params) != "avoided_name"


def test_a_cafe_then_a_dessert_shop_is_one_sitting() -> None:
    from app.domain.recommendation.style import one_sweet_stop

    day = template(
        Slot(1, "MEAL", 0.5),
        Slot(2, "CAFE", 0.2),
        Slot(3, "DESSERT", 0.1, is_optional=True),
        Slot(4, "BAR", 0.2),
    )
    [merged] = one_sweet_stop([day])
    assert [s.course_role for s in merged.slots] == ["MEAL", "CAFE", "BAR"]
    assert merged.slots[1].budget_share == pytest.approx(0.3) and merged.slots[1].is_optional is False
    apart = template(Slot(1, "CAFE", 0.2), Slot(2, "MEAL", 0.6), Slot(3, "DESSERT", 0.2))
    assert one_sweet_stop([apart]) == [apart]  # an afternoon coffee and an after-dinner sweet are two moments


def test_a_scene_adds_its_kind_of_place_without_losing_the_walk() -> None:
    from app.domain.recommendation.style import with_optional_after

    [day] = with_optional_after([DATE_EVENING], {"role": "CULTURE", "share": 0.12, "after": "ATTRACTION"})
    roles = [s.course_role for s in day.slots]
    assert roles.index("CULTURE") == roles.index("ATTRACTION") + 1
    culture = next(s for s in day.slots if s.course_role == "CULTURE")
    assert culture.is_optional and sum(s.budget_share for s in day.slots) == pytest.approx(
        sum(s.budget_share for s in DATE_EVENING.slots)
    )


def test_with_children_an_open_day_wraps_up_early() -> None:
    from datetime import datetime

    from app.domain.recommendation.budget import soft_window

    assert soft_window(datetime(2026, 9, 26, 18, 30), 20 * 60 + 30) == 120
    assert soft_window(datetime(2026, 9, 26, 19, 45), 20 * 60 + 30) == 90  # at least one sitting and a walk
    assert soft_window(datetime(2026, 9, 26, 12, 0), 20 * 60 + 30) == 510
    assert soft_window(datetime(2026, 9, 26, 12, 0), None) is None
