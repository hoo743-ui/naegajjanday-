"""꼭 들를 곳 (docs/59 #7): the errand's leg to or from the course, and a day that ends on the errand's side."""

from __future__ import annotations

import pytest

from app.domain.models import GeoPoint
from app.domain.recommendation.engine import RecommendationEngine
from app.domain.recommendation.errand import (
    END_PULL_CAP,
    TOWARD_SLACK_M,
    away_m,
    end_pull,
    errand_leg,
    heads_toward,
)
from app.domain.recommendation.itinerary import itinerary_rules
from tests.factories import DATE_EVENING, context, profile
from tests.unit.test_composer_engine import FakeSource, world

# 홍대: 걷고싶은거리 → 연남동 → 상수역. 애플 가로수길은 강남 쪽으로 약 9 km
HONGDAE_WALK = GeoPoint(37.5563, 126.9236)
YEONNAM = GeoPoint(37.5620, 126.9250)
SANGSU = GeoPoint(37.5478, 126.9227)
APPLE_GAROSU = GeoPoint(37.5205, 127.0229)


def test_a_day_ending_on_the_far_side_heads_away_from_the_errand() -> None:
    toward = [YEONNAM, HONGDAE_WALK, SANGSU]  # 상수 is the stop nearest 가로수길
    away = [SANGSU, HONGDAE_WALK, YEONNAM]
    assert away_m(toward, APPLE_GAROSU) == 0.0 and heads_toward(toward, APPLE_GAROSU)
    assert away_m(away, APPLE_GAROSU) > 400 and not heads_toward(away, APPLE_GAROSU)
    assert end_pull(toward, APPLE_GAROSU) == 0.0
    assert 0.02 < end_pull(away, APPLE_GAROSU) <= END_PULL_CAP
    # relative to the course's own nearest stop: a whole day further off costs nothing by itself
    assert end_pull([YEONNAM], APPLE_GAROSU) == 0.0
    assert end_pull([], APPLE_GAROSU) == 0.0


def test_the_leg_runs_from_the_errand_to_the_first_stop_or_from_the_last_stop_to_it() -> None:
    rules = itinerary_rules()
    stops = [YEONNAM, HONGDAE_WALK, SANGSU]
    before = errand_leg(APPLE_GAROSU, "before", stops, "walk", rules)
    after = errand_leg(APPLE_GAROSU, "after", stops, "walk", rules)
    assert before is not None and after is not None
    assert before.mode == after.mode == "transit"  # nine km is not walked
    assert before.distance_m > after.distance_m  # 연남 is further from 가로수길 than 상수
    assert before.minutes >= after.minutes >= 10
    # an errand that is one of the stops has no leg of its own
    assert errand_leg(SANGSU, "after", stops, "walk", rules) is None
    assert errand_leg(APPLE_GAROSU, "after", [], "walk", rules) is None
    near = errand_leg(GeoPoint(37.5485, 126.9227), "after", stops, "walk", rules)
    assert near is not None and near.mode == "walk"


@pytest.mark.parametrize("east", [True, False])
async def test_an_errand_after_the_day_pulls_its_last_stop_toward_it(east: bool) -> None:
    """The same world, an errand four km east or west: the day ends on that side."""
    places = world()
    far = 4000 / 88_000  # degrees of longitude ≈ 4 km at this latitude
    origin = context().origin
    errand = GeoPoint(origin.lat, origin.lng + (far if east else -far))
    engine = RecommendationEngine(FakeSource(places))
    plain = await engine.generate(context(algorithm="v2", alternatives=0), [DATE_EVENING], profile())
    pulled = await engine.generate(
        context(algorithm="v2", alternatives=0, end_point=errand), [DATE_EVENING], profile()
    )
    before = [s.place.point for s in plain.courses[0].stops]
    after = [s.place.point for s in pulled.courses[0].stops]
    assert away_m(after, errand) <= TOWARD_SLACK_M
    assert away_m(after, errand) <= away_m(before, errand)
