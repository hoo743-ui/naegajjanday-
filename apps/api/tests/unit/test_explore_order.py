"""Explore's nationwide list: the ranking stays, but no district or type takes the top in a row."""

from __future__ import annotations

from itertools import pairwise

from app.services.place_service import spread


def test_no_two_in_a_row_from_one_district_or_one_type() -> None:
    ranked = [("A", "market"), ("A", "market"), ("B", "market"), ("C", "park"), ("B", "museum")]
    out = spread(ranked, lambda r: r)
    assert out[0] == ("A", "market")  # the best one still leads
    # the first four can all differ from their neighbour: they do
    assert all(a[0] != b[0] and a[1] != b[1] for a, b in list(pairwise(out))[:3])
    assert sorted(out) == sorted(ranked)  # nothing dropped


def test_falls_back_to_the_best_left_when_nothing_differs() -> None:
    assert spread([("A", "x"), ("A", "x")], lambda r: r) == [("A", "x"), ("A", "x")]
