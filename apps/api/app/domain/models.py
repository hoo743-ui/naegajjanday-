"""Pure domain dataclasses. No framework / DB imports allowed in `app.domain`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

TransportMode = Literal["walk", "transit", "car"]

FEATURE_KEYS: tuple[str, ...] = (
    "budget",
    "distance",
    "rating",
    "sentiment",
    "congestion",
    "time_fit",
    "preference",
    "purpose_fit",
    "curated",  # listed by a public body (한국관광공사) — the selection signal we have instead of ratings
    "buzz",  # how packed the street around the place is; weight 0 unless a style asks for it
)


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float


@dataclass(frozen=True, slots=True)
class OpeningPeriod:
    """Minutes from 00:00 of `dow` (0=Mon … 6=Sun). `close_min` > 1440 means past midnight."""

    dow: int
    open_min: int
    close_min: int
    break_start_min: int | None = None
    break_end_min: int | None = None
    is_closed: bool = False


@dataclass(slots=True)
class PlaceCandidate:
    id: int
    public_id: str
    name: str
    category_code: str
    course_role: str
    lat: float
    lng: float
    price_per_person: int | None = None
    price_is_estimated: bool = False  # category-level prior, not a measured menu price
    is_free: bool = False
    address: str | None = None
    thumbnail_url: str | None = None
    default_stay_min: int = 60
    rating_avg: float | None = None
    rating_count: int = 0
    bayes_rating: float | None = None
    sentiment_score: float | None = None
    sentiment_count: int = 0
    aspect_scores: dict[str, float] = field(default_factory=dict)
    popularity: float = 0.0
    tags: dict[str, float] = field(default_factory=dict)
    opening_hours: list[OpeningPeriod] = field(default_factory=list)
    popular_times: dict[tuple[int, int], float] = field(default_factory=dict)
    approved_at: datetime | None = None
    is_overexposed: bool = False
    is_curated: bool = False
    buzz: float = 0.0  # set per request by style.assign_buzz
    is_event: bool = False
    category_name: str | None = None  # display label only; never used for scoring

    @property
    def point(self) -> GeoPoint:
        return GeoPoint(self.lat, self.lng)

    @property
    def price(self) -> int:
        return 0 if self.is_free or self.price_per_person is None else self.price_per_person

    @property
    def top_category(self) -> str:
        return self.category_code.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class Slot:
    position: int
    course_role: str
    budget_share: float
    is_optional: bool = False
    is_order_flexible: bool = False
    earliest_start_min: int | None = None
    latest_start_min: int | None = None
    min_slot_budget: int | None = None


@dataclass(frozen=True, slots=True)
class Template:
    id: int
    code: str
    purpose_code: str
    time_band: str
    min_budget_per_person: int
    party_min: int
    party_max: int
    slots: tuple[Slot, ...]


@dataclass(frozen=True, slots=True)
class ScoringParams:
    """Defaults are the initial values of doc 06; DB `scoring_profile.params` overrides them."""

    budget_target_util: float = 0.85
    budget_sigma: float = 0.18
    budget_sigma_low_factor: float = 1.6
    budget_over_slope: float = 4.0
    price_cap_ratio: float = 1.25
    free_score_small_share: float = 0.9
    free_score_other: float = 0.6
    free_share_threshold: float = 0.1
    distance_scale_m: float = 900.0
    distance_scale_transit_m: float = 2500.0
    distance_scale_car_m: float = 6000.0
    bayes_m: float = 30.0
    bayes_prior_default: float = 3.8
    sentiment_shrink_n: float = 15.0
    aspect_blend: float = 0.3
    aspect_weights: dict[str, float] = field(default_factory=dict)
    lambda_travel: float = 0.015
    lambda_overrun: float = 2.0
    diversity_bonus: float = 0.05
    utilization_bonus: float = 0.05
    utilization_lo: float = 0.8
    utilization_hi: float = 1.0
    budget_tolerance: float = 1.0  # the concept is "within MY budget" — not "about"
    beam_width: int = 40
    top_k: int = 12
    min_candidates: int = 5
    radius_expand_factor: float = 1.5
    radius_expand_max: int = 2
    max_leg_min_walk: float = 20.0
    max_leg_min_transit: float = 35.0
    max_leg_min_car: float = 40.0
    max_wait_min: int = 45
    group_min_party: int = 6
    group_tag: str | None = None
    exclude_tag_threshold: float = 0.6
    explore_penalty: float = 0.03
    explore_bonus: float = 0.03
    new_place_days: int = 14
    mmr_lambda: float = 0.7
    max_overlap: float = 0.5
    preference_prior: dict[str, float] = field(default_factory=dict)
    peak_curves: dict[str, list[list[float]]] = field(default_factory=dict)
    variants: list[dict[str, Any]] = field(default_factory=list)
    styles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ScoringParams:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (raw or {}).items() if k in known})

    def distance_scale(self, mode: str) -> float:
        return {
            "walk": self.distance_scale_m,
            "transit": self.distance_scale_transit_m,
            "car": self.distance_scale_car_m,
        }.get(mode, self.distance_scale_m)

    def max_leg_min(self, mode: str) -> float:
        return {
            "walk": self.max_leg_min_walk,
            "transit": self.max_leg_min_transit,
            "car": self.max_leg_min_car,
        }.get(mode, self.max_leg_min_walk)


@dataclass(frozen=True, slots=True)
class ScoringProfile:
    purpose_code: str
    version: int
    weights: dict[str, float]
    params: ScoringParams = field(default_factory=ScoringParams)

    @property
    def label(self) -> str:
        return f"{self.purpose_code}@v{self.version}"

    def normalized_weights(self) -> dict[str, float]:
        w = {k: max(0.0, float(self.weights.get(k, 0.0))) for k in FEATURE_KEYS}
        total = sum(w.values())
        if total <= 0:
            return {k: 1.0 / len(FEATURE_KEYS) for k in FEATURE_KEYS}
        return {k: v / total for k, v in w.items()}


@dataclass(slots=True)
class RequestContext:
    origin: GeoPoint
    radius_m: int
    purpose_code: str
    party_size: int
    budget_total: int
    start_at: datetime
    transport: TransportMode = "walk"
    duration_min: int | None = None
    style: str = "efficient"
    # style-level avoidance, per role: {"체인점": {"MEAL", "CAFE"}} — unlike disliked_tags (all roles)
    avoid_tags_by_role: dict[str, frozenset[str]] = field(default_factory=dict)
    # names of the chosen area itself ("경주 황리단길", "홍대"): a sight called exactly that is not a stop
    area_names: frozenset[str] = frozenset()
    include_roles: list[str] | None = None
    liked_tags: list[str] = field(default_factory=list)
    disliked_tags: list[str] = field(default_factory=list)
    category_weights: dict[str, float] = field(default_factory=dict)
    exclude_place_ids: set[int] = field(default_factory=set)
    purpose_tag_affinity: dict[str, float] = field(default_factory=dict)
    category_rating_avg: dict[str, float] = field(default_factory=dict)
    alternatives: int = 2

    @property
    def budget_per_person(self) -> float:
        return self.budget_total / max(1, self.party_size)


@dataclass(slots=True)
class StopResult:
    position: int
    role: str
    place: PlaceCandidate
    arrive_at: datetime
    leave_at: datetime
    est_price: int
    travel_min_from_prev: int
    distance_m_from_prev: int
    score: float
    score_breakdown: dict[str, float]
    congestion: float | None
    slot_budget: float  # effective b_s (allocated + carry-over)
    slot: Slot | None = None
    slot_share: float = 0.0
    slot_base_budget: float = 0.0


@dataclass(slots=True)
class CourseResult:
    label: str
    template_id: int
    stops: list[StopResult]
    total_price: int
    total_travel_min: int
    total_distance_m: int
    duration_min: int
    score: float
    objective: float
    optimizer: str
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def place_ids(self) -> frozenset[tuple[bool, int]]:
        return frozenset((s.place.is_event, s.place.id) for s in self.stops)


@dataclass(slots=True)
class EngineOutput:
    courses: list[CourseResult]
    template: Template
    candidates_count: int
    warnings: list[dict[str, Any]] = field(default_factory=list)
    stay_scale: float = 1.0


class DomainError(Exception):
    """Base class for domain-level failures (mapped to problem responses by the API layer)."""


class BudgetTooLowError(DomainError):
    def __init__(self, min_budget: int) -> None:
        super().__init__(f"budget too low, min={min_budget}")
        self.min_budget = min_budget


class NoTemplateError(DomainError):
    pass


class NoCourseError(DomainError):
    pass
