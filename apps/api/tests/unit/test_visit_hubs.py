"""Where people really go (navigation ranks): names, ranks and matching — no network, no database."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.infra.ingestion.bulk.visit_hubs import (
    Hub,
    _months,
    name_parts,
    pick_existing,
    popularity_of,
    read_hubs,
)
from app.infra.ingestion.dedupe import ExistingPlace


def hub(name: str, lat: float = 37.5, lng: float = 127.0, rank: int = 1) -> Hub:
    return Hub("c1", name, lat, lng, rank, "202608", "", "", "", "", name_parts(name))


def test_a_branch_is_never_a_name_of_its_own() -> None:
    assert name_parts("Mall/North branch") == ("Mall North branch", "Mall")
    assert name_parts("Film scene/(Long Beach)") == ("Film scene Long Beach", "Film scene", "Long Beach")
    assert name_parts("Palace") == ("Palace",)


def test_rank_one_is_the_most_popular_and_rank_hundred_barely_counts() -> None:
    assert popularity_of(1, 100) == 1.0
    assert popularity_of(30, 100) == 0.71
    assert popularity_of(100, 100) == 0.01


def test_last_month_comes_first_and_the_year_rolls_back() -> None:
    assert _months(date(2026, 2, 10), 3) == ["202601", "202512", "202511"]


def test_the_closest_good_name_wins_and_a_far_one_never_does() -> None:
    near = ExistingPlace(1, "Mall North branch", 37.5005, 127.0, None)
    shop_inside = ExistingPlace(2, "Noodle house North branch", 37.5001, 127.0, None)
    far = ExistingPlace(3, "Mall North branch", 37.6, 127.0, None)
    picked = pick_existing(
        hub("Mall/North branch"), [shop_inside, far, near], radius_m=400, min_similarity=0.74
    )
    assert picked is near
    assert (
        pick_existing(hub("Mall/North branch"), [shop_inside, far], radius_m=400, min_similarity=0.74) is None
    )


def test_a_one_letter_name_is_compared_as_it_is() -> None:
    assert name_parts("K") == ()  # too short to be an alias …
    same = ExistingPlace(1, "K", 37.5, 127.0, None)
    assert pick_existing(hub("K"), [same], radius_m=400, min_similarity=0.74) is same  # … but still a name


def test_a_place_listed_by_two_districts_keeps_its_better_rank(tmp_path: Path) -> None:
    row = {"hubTatsCd": "a", "hubTatsNm": "Lake", "mapX": "127.1", "mapY": "37.4", "baseYm": "202608",
           "hubCtgryLclsNm": "L", "hubCtgryMclsNm": "M", "areaNm": "A", "signguNm": "S"}  # fmt: skip
    (tmp_path / "11110.json").write_text(json.dumps([{**row, "hubRank": "40"}]), encoding="utf-8")
    (tmp_path / "11140.json").write_text(
        json.dumps(
            [{**row, "hubRank": "7"}, {**row, "hubTatsCd": "b", "hubRank": "1", "mapX": "0", "mapY": "0"}]
        ),
        encoding="utf-8",
    )
    (tmp_path / "11170.json").write_text("[]", encoding="utf-8")  # a district with nothing
    hubs = read_hubs(tmp_path)
    assert [(h.code, h.rank) for h in hubs] == [("a", 7)]  # and the one with no coordinates is dropped
