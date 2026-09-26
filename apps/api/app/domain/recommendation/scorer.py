"""S(p | ctx) = Σ w_k · f_k(p, ctx). Returns the weighted sum together with its breakdown."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.models import PlaceCandidate, RequestContext, ScoringProfile
from app.domain.recommendation import features as F
from app.domain.recommendation.familiarity import familiarity_rules, is_regular, novelty_pull
from app.domain.signature import get_signature_rules


@dataclass(frozen=True, slots=True)
class ScoreInput:
    place: PlaceCandidate
    slot_budget: float
    slot_share: float
    distance_m: float
    arrive_at: datetime
    stay_min: int


@dataclass(frozen=True, slots=True)
class Score:
    total: float
    breakdown: dict[str, float]


class PlaceScorer:
    """Feature extraction is kept separate from weighting so a learned ranker can reuse it (doc 06 §8)."""

    def __init__(self, profile: ScoringProfile, ctx: RequestContext) -> None:
        self._profile = profile
        self._weights = profile.normalized_weights()
        self._ctx = ctx
        self._listed_score = get_signature_rules().listed_score
        # a regular (recommendation.familiarity): what everyone is sent to here counts for less
        self._known_scale = familiarity_rules().regular.known_scale if is_regular(ctx) else 1.0

    @property
    def profile(self) -> ScoringProfile:
        return self._profile

    def features(self, x: ScoreInput) -> dict[str, float]:
        p, params, ctx = x.place, self._profile.params, self._ctx
        bayes = p.bayes_rating
        if bayes is None:
            prior = ctx.category_rating_avg.get(p.category_code, params.bayes_prior_default)
            bayes = F.bayesian_rating(p.rating_avg, p.rating_count, prior, params.bayes_m)
        return {
            "budget": F.budget_fit(p.price_per_person, p.is_free, x.slot_budget, x.slot_share, params),
            # v1 feeds the hop from the previous stop here (the bundle effect); v2 (docs/29) feeds the
            # distance from the area's centre — where the area is liveliest — and prices hops in the day score
            "distance": F.distance_fit(x.distance_m, params.distance_scale(ctx.transport)),
            "rating": F.rating_fit(bayes),
            "sentiment": F.sentiment_fit(p.sentiment_score, p.sentiment_count, p.aspect_scores, params),
            "congestion": F.congestion_fit(F.congestion_at(p, x.arrive_at)),
            "time_fit": F.time_fit(p, x.arrive_at, x.stay_min, params),
            "preference": F.preference_fit(
                p, ctx.liked_tags, ctx.disliked_tags, ctx.category_weights, params, now=ctx.start_at
            ),
            "purpose_fit": F.purpose_fit(p.tags, ctx.purpose_tag_affinity),
            # how much this place stands for the neighbourhood: a local specialty or landmark in full, a
            # tourism-board listing a little less
            # vouched for (a public mark), what the district is known for, or simply where people
            # really go (measured navigation rank, 1.0 = first in its district): the best of the three
            "curated": self._known_scale
            * max(p.local_score, self._listed_score if p.is_curated else 0.0, p.popularity),
            "buzz": p.buzz,
        }

    def score(self, x: ScoreInput) -> Score:
        feats = self.features(x)
        total = (
            sum(self._weights[k] * v for k, v in feats.items())
            + trait_pull(x.place, self._ctx.trait_pull)
            + x.place.local_pull  # what the neighbourhood is for, beyond a public listing (signature)
            + novelty_pull(x.place, self._ctx)  # a regular: newly opened · lesser-known (familiarity)
        )
        return Score(total=round(total, 4), breakdown={k: round(v, 4) for k, v in feats.items()})


def trait_pull(place: PlaceCandidate, pull: dict[str, float]) -> float:
    """A wish about the kind of place, not a tag (docs/30): "photo" pulls toward places with a photo of their
    own (only real photos of the place are stored, never a category stand-in), "free" toward places that cost
    nothing, "buzz" (negative for "quiet") away from the packed streets. Not a feature of its own: the
    breakdown the page explains stays the same."""
    if not pull:
        return 0.0
    out = 0.0
    if place.thumbnail_url:
        out += pull.get("photo", 0.0)
    if place.price == 0:
        out += pull.get("free", 0.0)
    out += pull.get("buzz", 0.0) * place.buzz
    # 누구와 (docs/48): the kind of place this company likes — the most specific code the pull names
    parts = place.category_code.split(".")
    for depth in range(len(parts), 0, -1):
        if (cat := pull.get("cat:" + ".".join(parts[:depth]))) is not None:
            out += cat
            break
    return out
