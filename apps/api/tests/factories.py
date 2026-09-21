from __future__ import annotations

from datetime import datetime
from itertools import count
from zoneinfo import ZoneInfo

from app.domain.models import (
    GeoPoint,
    OpeningPeriod,
    PlaceCandidate,
    RequestContext,
    ScoringParams,
    ScoringProfile,
    Slot,
    Template,
)

KST = ZoneInfo("Asia/Seoul")
ORIGIN = GeoPoint(37.5572, 126.9245)
SUNDAY_6PM = datetime(2026, 9, 20, 18, 0, tzinfo=KST)  # weekday() == 6
DEFAULT_WEIGHTS = {
    "budget": 0.24,
    "distance": 0.12,
    "rating": 0.16,
    "sentiment": 0.14,
    "congestion": 0.08,
    "time_fit": 0.08,
    "preference": 0.12,
    "purpose_fit": 0.06,
}
_ids = count(1)


def all_week(open_min: int, close_min: int, **kwargs: int) -> list[OpeningPeriod]:
    return [OpeningPeriod(d, open_min, close_min, **kwargs) for d in range(7)]


def place(
    role: str = "MEAL",
    category: str = "food.korean",
    price: int | None = 10000,
    *,
    dlat: float = 0.0,
    dlng: float = 0.0,
    **kwargs: object,
) -> PlaceCandidate:
    i = next(_ids)
    defaults: dict[str, object] = {
        "id": i,
        "public_id": f"p-{i}",
        "name": f"place-{i}",
        "category_code": category,
        "course_role": role,
        "lat": ORIGIN.lat + dlat,
        "lng": ORIGIN.lng + dlng,
        "price_per_person": price,
        "is_free": price is None,
        "rating_avg": 4.3,
        "rating_count": 200,
        "sentiment_score": 0.5,
        "sentiment_count": 80,
        "default_stay_min": 60,
    }
    defaults.update(kwargs)
    return PlaceCandidate(**defaults)  # type: ignore[arg-type]


def context(budget_total: int = 40000, party_size: int = 2, **kwargs: object) -> RequestContext:
    defaults: dict[str, object] = {
        "origin": ORIGIN,
        "radius_m": 1200,
        "purpose_code": "date",
        "party_size": party_size,
        "budget_total": budget_total,
        "start_at": SUNDAY_6PM,
    }
    defaults.update(kwargs)
    return RequestContext(**defaults)  # type: ignore[arg-type]


def profile(**params: object) -> ScoringProfile:
    return ScoringProfile("date", 1, dict(DEFAULT_WEIGHTS), ScoringParams(**params))  # type: ignore[arg-type]


def template(*slots: Slot, min_budget: int = 8000, time_band: str = "evening", tid: int = 1) -> Template:
    return Template(tid, f"t-{tid}", "date", time_band, min_budget, 1, 8, tuple(slots))


DATE_EVENING = template(
    Slot(1, "MEAL", 0.55),
    Slot(2, "CAFE", 0.20),
    Slot(3, "ATTRACTION", 0.05),
    Slot(4, "BAR", 0.20, is_optional=True, earliest_start_min=17 * 60, min_slot_budget=12000),
)
