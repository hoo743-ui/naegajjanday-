"""Stored estimates follow the price prior (bulk/reprice.py)."""

from __future__ import annotations

from app.infra.ingestion.bulk.price_prior import PricePrior
from app.infra.ingestion.bulk.reprice import new_price

PRIOR = PricePrior.from_data(
    {
        "by_semas_code": {"I21104": 19000},
        "by_category": {"bar": 19000, "activity.fortune": 15000},
        "name_rules": [{"contains": ["생활맥주"], "categories": ["bar"], "price": 16000}],
    },
    {"sido": [{"name": "서울특별시", "cost_factor": 1.0}, {"name": "제주특별자치도", "cost_factor": 1.1}]},
)
CATEGORIES = {"I21104": "bar", "I21201": "cafe"}


def test_the_source_code_price_scaled_by_region() -> None:
    raw = {"code": "I21104", "sido": "제주특별자치도"}
    assert new_price(PRIOR, CATEGORIES, "bar", raw, "동네술집") == 20900


def test_a_name_rule_wins_and_a_moved_place_is_priced_as_what_it_is() -> None:
    assert (
        new_price(PRIOR, CATEGORIES, "bar", {"code": "I21104", "sido": "서울특별시"}, "생활맥주 강남점")
        == 16000
    )
    # filed as a café, moved to 타로 by its name: not the café code's price
    assert (
        new_price(PRIOR, CATEGORIES, "activity.fortune", {"code": "I21201", "sido": "서울특별시"}, "타로")
        == 15000
    )
