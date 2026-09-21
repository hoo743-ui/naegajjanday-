from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from app.domain.models import OpeningPeriod, ScoringParams
from app.domain.recommendation import features as F
from tests.factories import KST, SUNDAY_6PM, all_week, place

P = ScoringParams()


def fit(price: int, budget: float = 10000) -> float:
    return F.budget_fit(price, False, budget, 0.5, P)


class TestBudgetFit:
    def test_peaks_at_target_utilization(self) -> None:
        assert fit(8500) == pytest.approx(1.0)
        grid = {u: fit(int(u * 100)) for u in range(10, 125, 5)}
        assert max(grid, key=lambda u: grid[u]) == 85

    def test_cheap_side_is_gentler_than_expensive_side(self) -> None:
        # same distance (0.15) from the target: below uses sigma x 1.6
        assert fit(7000) > fit(10000)
        assert fit(7000) == pytest.approx(math.exp(-(0.15**2) / (2 * (0.18 * 1.6) ** 2)))

    def test_far_too_cheap_is_penalized(self) -> None:
        assert fit(1500) < 0.1

    def test_over_budget_drops_steeply_and_hits_zero(self) -> None:
        at_budget = fit(10000)
        assert fit(10500) == pytest.approx(at_budget - 4 * 0.05)
        assert fit(11000) < fit(10500) < at_budget
        assert fit(12500) == 0.0  # f(1) - 4 * 0.25 < 0
        assert fit(13000) == 0.0  # beyond the 1.25 hard cap

    def test_free_place_rule(self) -> None:
        assert F.budget_fit(None, True, 1000, 0.05, P) == 0.9
        assert F.budget_fit(0, True, 1000, 0.10, P) == 0.9
        assert F.budget_fit(None, True, 8000, 0.40, P) == 0.6

    def test_paid_place_in_zero_budget_slot(self) -> None:
        assert F.budget_fit(5000, False, 0, 0.0, P) == 0.0


class TestRating:
    def test_few_perfect_reviews_lose_to_many_good_ones(self) -> None:
        newcomer = F.bayesian_rating(5.0, 3, prior_mean=4.0, m=30)
        veteran = F.bayesian_rating(4.5, 800, prior_mean=4.0, m=30)
        assert newcomer == pytest.approx((3 * 5.0 + 30 * 4.0) / 33)
        assert veteran > newcomer

    def test_no_reviews_returns_prior(self) -> None:
        assert F.bayesian_rating(None, 0, 3.9, 30) == 3.9

    def test_rating_fit_is_clipped(self) -> None:
        assert F.rating_fit(2.0) == 0.0
        assert F.rating_fit(4.0) == 0.5
        assert F.rating_fit(5.5) == 1.0

    def test_zscore_normalizes_generous_and_strict_providers(self) -> None:
        # naver 4.6 (mean 4.4, sd .3) and google 4.0 (mean 3.8, sd .3) are both +0.67 sd
        merged = F.zscore_weighted_rating([(4.6, 100, 4.4, 0.3), (4.0, 100, 3.8, 0.3)], 4.0, 0.4)
        assert merged == pytest.approx(4.0 + (0.2 / 0.3) * 0.4)


class TestSentiment:
    def test_shrinkage_towards_neutral(self) -> None:
        assert F.sentiment_fit(0.8, 15, None, P) == pytest.approx((0.8 * 15 / 30 + 1) / 2)
        assert F.sentiment_fit(0.8, 3, None, P) < F.sentiment_fit(0.8, 300, None, P)
        assert F.sentiment_fit(0.8, 300, None, P) < 0.9

    def test_missing_data_is_neutral(self) -> None:
        assert F.sentiment_fit(None, 0, None, P) == 0.5
        assert F.sentiment_fit(0.9, 0, None, P) == 0.5

    def test_aspect_weights_boost(self) -> None:
        dating = ScoringParams(aspect_weights={"mood": 1.0})
        moody = F.sentiment_fit(0.2, 200, {"mood": 0.95, "price": 0.1}, dating)
        plain = F.sentiment_fit(0.2, 200, {"mood": 0.20, "price": 0.9}, dating)
        assert moody > plain

    def test_recency_half_life(self) -> None:
        now = datetime(2026, 9, 20, tzinfo=KST)
        score = F.recency_weighted_sentiment([(1.0, now), (-1.0, now - timedelta(days=180))], now)
        assert score == pytest.approx((1.0 - 0.5) / 1.5)
        assert F.recency_weighted_sentiment([], now) is None


class TestTimeAndCongestion:
    def test_open_break_and_closed_day(self) -> None:
        hours = [*all_week(11 * 60, 22 * 60, break_start_min=15 * 60, break_end_min=17 * 60)[:6]]
        hours.append(OpeningPeriod(6, 0, 0, is_closed=True))
        saturday = SUNDAY_6PM - timedelta(days=1)
        assert F.is_open(hours, saturday)
        assert not F.is_open(hours, saturday.replace(hour=15, minute=30))  # break time
        assert not F.is_open(hours, SUNDAY_6PM)  # closed on Sundays
        assert F.minutes_until_close(hours, saturday.replace(hour=14, minute=0)) == 60  # until the break

    def test_past_midnight_period_belongs_to_previous_day(self) -> None:
        bar = all_week(18 * 60, 26 * 60)
        assert F.is_open(bar, SUNDAY_6PM.replace(hour=1, minute=0))
        assert F.minutes_until_close(bar, SUNDAY_6PM.replace(hour=1, minute=0)) == 60
        assert not F.is_open(bar, SUNDAY_6PM.replace(hour=3, minute=0))

    def test_no_hours_means_always_open(self) -> None:
        assert math.isinf(F.minutes_until_close([], SUNDAY_6PM) or 0)

    def test_time_fit_penalizes_closing_soon(self) -> None:
        late = place(opening_hours=all_week(11 * 60, 19 * 60))
        roomy = place(opening_hours=all_week(11 * 60, 23 * 60))
        assert F.time_fit(roomy, SUNDAY_6PM, 60, P) > F.time_fit(late, SUNDAY_6PM, 60, P)
        assert F.time_fit(late, SUNDAY_6PM.replace(hour=20), 60, P) == 0.0

    def test_peak_curve_for_bar(self) -> None:
        assert F.peak_fit("BAR", SUNDAY_6PM.replace(hour=21)) == 1.0
        assert F.peak_fit("BAR", SUNDAY_6PM.replace(hour=13)) == F.PEAK_FLOOR
        assert F.peak_fit("BAR", SUNDAY_6PM, {"BAR": [[0, 24, 0.4]]}) == 0.4

    def test_congestion(self) -> None:
        p = place(popular_times={(6, 18): 0.9})
        assert F.congestion_fit(F.congestion_at(p, SUNDAY_6PM)) == pytest.approx(0.1)
        assert F.congestion_fit(None) == 0.5


class TestPreferenceAndPurpose:
    def test_cosine_preference(self) -> None:
        quiet = place(tags={"조용한": 1.0})
        loud = place(tags={"활기찬": 1.0})
        assert (
            F.preference_fit(quiet, ["조용한"], [], {}, P)
            > 0.5
            > F.preference_fit(loud, [], ["활기찬"], {}, P)
        )

    def test_cold_start_uses_prior_then_neutral(self) -> None:
        p = place(tags={"로맨틱": 1.0})
        assert F.preference_fit(p, [], [], {}, P) == 0.5
        assert F.preference_fit(p, [], [], {}, ScoringParams(preference_prior={"로맨틱": 0.7})) > 0.5

    def test_exploration_bonus_and_penalty(self) -> None:
        fresh = place(approved_at=SUNDAY_6PM - timedelta(days=3))
        hot = place(is_overexposed=True)
        assert F.preference_fit(fresh, [], [], {}, P, now=SUNDAY_6PM) == pytest.approx(0.53)
        assert F.preference_fit(hot, [], [], {}, P, now=SUNDAY_6PM) == pytest.approx(0.47)

    def test_purpose_fit_weighted_mean(self) -> None:
        affinity = {"조용한": 0.8, "단체석": -0.3}
        assert F.purpose_fit({"조용한": 1.0}, affinity) == pytest.approx(0.9)
        assert F.purpose_fit({"조용한": 1.0, "단체석": 1.0}, affinity) == pytest.approx((0.25 + 1) / 2)
        assert F.purpose_fit({"기타": 1.0}, affinity) == 0.5

    def test_distance_decay(self) -> None:
        assert F.distance_fit(0, 900) == 1.0
        assert F.distance_fit(900, 900) == pytest.approx(math.exp(-1))
