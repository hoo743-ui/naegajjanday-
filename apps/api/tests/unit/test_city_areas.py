"""A whole city as the destination: clusters of well-visited sights, a few per day, no zigzag."""

from __future__ import annotations

from app.domain.models import GeoPoint
from app.domain.recommendation.itinerary import areas_by_day, cluster_areas, route_areas

# two sights by the sea, two downtown 10 km away, one alone in the hills far off
SIGHTS = [
    (1, "beach", GeoPoint(35.10, 129.10), 1.0),
    (2, "pier", GeoPoint(35.105, 129.105), 0.6),
    (3, "market", GeoPoint(35.10, 129.00), 0.9),
    (4, "tower", GeoPoint(35.102, 129.003), 0.5),
    (5, "temple", GeoPoint(35.30, 129.00), 0.4),
]


def test_the_most_visited_sight_names_its_area_and_takes_its_neighbours() -> None:
    areas = cluster_areas(SIGHTS, radius_m=2500, limit=5)
    assert [(a.name, a.place_ids) for a in areas] == [("beach", (1, 2)), ("market", (3, 4)), ("temple", (5,))]
    assert [round(a.weight, 1) for a in areas] == [1.6, 1.4, 0.4]
    assert [a.name for a in cluster_areas(SIGHTS, radius_m=2500, limit=2)] == ["beach", "market"]


def test_the_route_starts_at_the_best_area_and_goes_to_the_nearest_next() -> None:
    far, mid, best = (
        cluster_areas(SIGHTS, 2500, 5)[2],
        cluster_areas(SIGHTS, 2500, 5)[1],
        cluster_areas(SIGHTS, 2500, 5)[0],
    )
    assert [a.name for a in route_areas([best, far, mid])] == ["beach", "market", "temple"]


def test_a_day_keeps_to_its_own_side_of_the_city() -> None:
    areas = cluster_areas(SIGHTS, 2500, 5)  # beach · market (10 km west of it) · temple (22 km north)
    names = lambda days: [[a.name for a in day] for day in days]  # noqa: E731
    # within 12 km the market joins the beach; the temple is a day of its own
    assert names(areas_by_day(areas, days=2, per_day=2, span_m=12000)) == [["beach", "market"], ["temple"]]
    # within 5 km nothing joins anything: the two best areas get a day each
    assert names(areas_by_day(areas, days=2, per_day=2, span_m=5000)) == [["beach"], ["market"]]
    # fewer areas than days: the best one again (the engine never repeats a place)
    assert names(areas_by_day(areas[:1], days=2, per_day=1)) == [["beach"], ["beach"]]
    assert areas_by_day([], days=2, per_day=2) == [[], []]
