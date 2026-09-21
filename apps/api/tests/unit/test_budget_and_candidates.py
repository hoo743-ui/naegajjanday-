from __future__ import annotations

import pytest

from app.domain.models import BudgetTooLowError, ScoringParams, Slot
from app.domain.recommendation import budget as B
from app.domain.recommendation.candidates import FilterContext, hard_filter, rejection_reason
from tests.factories import DATE_EVENING, SUNDAY_6PM, all_week, context, place, template

P = ScoringParams(group_tag="단체석")


class TestAllocation:
    def test_shares_times_budget(self) -> None:
        slots = B.allocate(DATE_EVENING, 100_000)
        assert [round(s.budget) for s in slots] == [55000, 20000, 5000, 20000]

    def test_optional_slot_is_dropped_and_shares_renormalized(self) -> None:
        slots = B.allocate(DATE_EVENING, 20_000)  # BAR would get 4,000 < min_slot_budget 12,000
        assert [s.slot.course_role for s in slots] == ["MEAL", "CAFE", "ATTRACTION"]
        assert sum(s.share for s in slots) == pytest.approx(1.0)
        assert [round(s.budget) for s in slots] == [13750, 5000, 1250]

    def test_free_slot_keeps_zero_share(self) -> None:
        t = template(Slot(1, "MEAL", 1.0), Slot(2, "NIGHTVIEW", 0.0))
        assert [s.budget for s in B.allocate(t, 15000)] == [15000, 0]

    def test_include_roles_filter(self) -> None:
        slots = B.allocate(DATE_EVENING, 100_000, include_roles=["MEAL", "CAFE"])
        assert [s.slot.course_role for s in slots] == ["MEAL", "CAFE"]
        assert sum(s.share for s in slots) == pytest.approx(1.0)

    def test_carry_over(self) -> None:
        assert B.carry_over([11000], [7000]) == 4000
        assert B.effective_budget(4000, 4000) == 8000
        assert B.effective_budget(4000, -9000) == 0  # earlier overspend shrinks the slot, never below 0

    def test_drop_slot_hands_share_to_the_rest(self) -> None:
        slots = B.drop_slot(B.allocate(DATE_EVENING, 100_000), position=4, budget_per_person=100_000)
        assert sum(s.budget for s in slots) == pytest.approx(100_000)


class TestFitToDuration:
    """만나는 시간이 짧으면 체류를 반으로 깎는 대신 들르는 곳 수를 줄인다."""

    def _roles(self, duration: int | None) -> list[str]:
        kept, _ = B.fit_to_duration(B.allocate(DATE_EVENING, 100_000), duration, 100_000)
        return [s.slot.course_role for s in kept]

    def test_no_duration_keeps_the_template(self) -> None:
        assert self._roles(None) == ["MEAL", "CAFE", "ATTRACTION", "BAR"]

    def test_long_window_keeps_everything(self) -> None:
        assert self._roles(300) == ["MEAL", "CAFE", "ATTRACTION", "BAR"]

    def test_optional_goes_first_then_smallest_share(self) -> None:
        assert self._roles(180) == ["MEAL", "CAFE", "ATTRACTION"]
        assert self._roles(120) == ["MEAL", "CAFE"]

    def test_anchor_slot_survives_the_shortest_window(self) -> None:
        assert self._roles(60) == ["MEAL"]

    def test_budget_is_handed_to_the_remaining_slots(self) -> None:
        kept, dropped = B.fit_to_duration(B.allocate(DATE_EVENING, 100_000), 120, 100_000)
        assert sum(s.budget for s in kept) == pytest.approx(100_000)
        assert [s.course_role for s in dropped] == ["BAR", "ATTRACTION"]

    def test_slot_that_opens_after_the_window_is_dropped_first(self) -> None:
        """11:00~15:00 약속에 17시부터 여는 술집 슬롯은 쓸 데가 없다 — 슬롯 수가 남아도 뺀다."""
        slots = B.allocate(DATE_EVENING, 100_000)
        kept, dropped = B.fit_to_duration(slots, 240, 100_000, start_min=11 * 60)
        assert [s.slot.course_role for s in kept] == ["MEAL", "CAFE", "ATTRACTION"]
        assert [s.course_role for s in dropped] == ["BAR"]
        # 18:00 에 시작하면 같은 4시간이라도 술집이 창 안에 들어온다
        kept, _ = B.fit_to_duration(slots, 240, 100_000, start_min=18 * 60)
        assert [s.slot.course_role for s in kept] == ["MEAL", "CAFE", "ATTRACTION", "BAR"]


class TestTemplateSelection:
    def test_prefers_time_band_and_richest_affordable(self) -> None:
        lunch = template(Slot(1, "MEAL", 1.0), min_budget=6000, time_band="lunch", tid=1)
        basic = template(Slot(1, "MEAL", 1.0), min_budget=8000, tid=2)
        fancy = template(Slot(1, "MEAL", 1.0), min_budget=30000, tid=3)
        pick = B.select_template(
            [lunch, basic, fancy], time_band="evening", party_size=2, budget_per_person=20000
        )
        assert pick.id == 2
        pick = B.select_template(
            [lunch, basic, fancy], time_band="evening", party_size=2, budget_per_person=50000
        )
        assert pick.id == 3

    def test_budget_too_low_reports_minimum_for_party(self) -> None:
        with pytest.raises(BudgetTooLowError) as exc:
            B.select_template([DATE_EVENING], time_band="evening", party_size=2, budget_per_person=3000)
        assert exc.value.min_budget == 16000

    def test_time_band(self) -> None:
        assert B.time_band_for(SUNDAY_6PM, None) == "evening"
        assert B.time_band_for(SUNDAY_6PM.replace(hour=12), None) == "lunch"
        assert B.time_band_for(SUNDAY_6PM.replace(hour=15), None) == "afternoon"
        assert B.time_band_for(SUNDAY_6PM.replace(hour=10), 480) == "fullday"
        assert B.time_band_for(SUNDAY_6PM.replace(hour=12), 360) == "fullday"  # 반나절
        assert B.time_band_for(SUNDAY_6PM.replace(hour=12), 240) == "lunch"
        # 저녁에 시작하는 긴 약속은 식사가 한 번뿐이다 → 저녁 템플릿 그대로
        assert B.time_band_for(SUNDAY_6PM, 360) == "evening"


class TestHardFilters:
    def fc(self, budget: float = 10000, **ctx_kwargs: object) -> FilterContext:
        return FilterContext.build(context(**ctx_kwargs), "MEAL", budget, SUNDAY_6PM)

    def test_price_cap_is_125_percent(self) -> None:
        assert rejection_reason(place(price=12500), self.fc(), P) is None
        assert rejection_reason(place(price=12600), self.fc(), P) == "price_cap"
        assert rejection_reason(place(price=None), self.fc(budget=0), P) is None  # free is always ok

    def test_break_time_and_closing_soon(self) -> None:
        on_break = place(
            opening_hours=all_week(11 * 60, 22 * 60, break_start_min=17 * 60, break_end_min=19 * 60)
        )
        closing = place(opening_hours=all_week(11 * 60, 18 * 60 + 20))
        open_late = place(opening_hours=all_week(11 * 60, 22 * 60))
        assert rejection_reason(on_break, self.fc(), P) == "closed"
        assert rejection_reason(closing, self.fc(), P) == "closed"
        assert rejection_reason(open_late, self.fc(), P) is None

    def test_exclusions(self) -> None:
        waiting = place(tags={"웨이팅": 0.9})
        banned = place()
        fc = self.fc(disliked_tags=["웨이팅"], exclude_place_ids={banned.id})
        assert rejection_reason(waiting, fc, P) == "excluded_tag"
        assert rejection_reason(banned, fc, P) == "excluded_place"
        assert rejection_reason(place(tags={"웨이팅": 0.3}), fc, P) is None  # weak tag → soft penalty only

    def test_group_capacity_and_role(self) -> None:
        big = self.fc(party_size=6, budget_total=120000)
        assert rejection_reason(place(), big, P) == "capacity"
        assert rejection_reason(place(tags={"단체석": 0.8}), big, P) is None
        assert rejection_reason(place(role="CAFE", category="cafe.coffee"), self.fc(), P) == "role"

    def test_hard_filter_keeps_only_valid(self) -> None:
        good, pricey = place(price=9000), place(price=20000)
        assert hard_filter([good, pricey], self.fc(), P) == [good]
