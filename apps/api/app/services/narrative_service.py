"""Course narrative (doc 06 §7). The LLM only phrases structured facts; when there is no key or the
call fails, the template narrative from the prompt layer is used and the user never notices."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.domain.models import CourseResult, StopResult
from app.infra.llm.base import LLMError, LLMMessage, LLMProvider, LLMRequest
from app.prompts.loader import Prompt, PromptLoader

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Narrative:
    summary: str
    reasons: dict[int, str]  # position -> reason
    tip: str | None
    source: str  # "template" | "<prompt ref>"

    def as_text(self) -> str:
        """The streamed paragraph: summary, one numbered line per stop, tip."""
        marks = "①②③④⑤⑥⑦⑧⑨⑩"
        lines = [
            f"{marks[i] if i < len(marks) else f'{i + 1}.'} {self.reasons[k]}"
            for i, k in enumerate(sorted(self.reasons))
        ]
        parts = [self.summary, *lines]
        if self.tip:
            parts.append(self.tip)
        return "\n".join(parts)


def _won(value: int) -> str:
    return f"{value:,}"


class NarrativeService:
    def __init__(self, prompts: PromptLoader, llm: LLMProvider) -> None:
        self._prompts = prompts
        self._llm = llm

    # --- template fallback -------------------------------------------------------------------

    def congestion_level(self, value: float) -> str:
        levels = self._prompts.get("narrative_fallback").data["congestion_levels"]
        return next((lv["label"] for lv in levels if value < lv["max"]), levels[-1]["label"])

    def template(
        self,
        course: CourseResult,
        *,
        party_size: int,
        budget_total: int,
        transport: str,
        tag_affinity: Mapping[str, float] | None = None,
    ) -> Narrative:
        fb = self._prompts.get("narrative_fallback")
        d = fb.data
        party = d["party_labels"].get(party_size) or fb.render_text(d["party_default"], party_size=party_size)
        key = "summary" if course.total_travel_min > 0 else "summary_no_travel"
        summary = fb.render_text(
            d[key],
            party=party,
            price=_won(course.total_price),
            transport=d["transport_labels"].get(transport, ""),
            travel_min=course.total_travel_min,
        )
        if "bodies" in d:  # v2+: itinerary-style lines in Jjani's voice
            last = max((s.position for s in course.stops), default=0)
            # Variety: the n-th stop of a role takes the n-th variant, so two cafés in one course never
            # read the same; the course-level offset keeps different courses from sounding identical.
            offset = course.stops[0].place.id if course.stops else 0
            seen_roles: dict[str, int] = {}
            reasons = {}
            for s in sorted(course.stops, key=lambda x: x.position):
                nth = seen_roles.get(s.role, 0)
                seen_roles[s.role] = nth + 1
                reasons[s.position] = self._stop_line(
                    fb,
                    s,
                    party=party,
                    transport=transport,
                    last=last,
                    tag_affinity=tag_affinity or {},
                    seed=offset + nth,
                )
        else:  # v1 (pinned for a rollback): top score features + tail
            reasons = {s.position: self._reason(fb, s, tag_affinity or {}) for s in course.stops}
        return Narrative(summary, reasons, self._tip(fb, course, budget_total), "template")

    @staticmethod
    def _pick(options: list[str], seed: int) -> str:
        """Deterministic variety: the same course always reads the same, neighbours read differently."""
        return options[seed % len(options)]

    @staticmethod
    def category_word(fb: Prompt, category_code: str) -> str:
        words: dict[str, str] = fb.data["category_words"]
        parts = category_code.split(".")
        while parts:  # 'food.korean.bbq' → 'food.korean' → 'food'
            if (word := words.get(".".join(parts))) is not None:
                return word
            parts.pop()
        return str(fb.data.get("category_word_default", ""))

    @classmethod
    def _stop_line(
        cls,
        fb: Prompt,
        stop: StopResult,
        *,
        party: str,
        transport: str,
        last: int,
        tag_affinity: Mapping[str, float],
        seed: int,
    ) -> str:
        d = fb.data
        leads = d["leads"]
        if last <= 1:
            lead = cls._pick(leads["only"], seed)
        elif stop.position == 1:
            lead = cls._pick(leads["first"], seed)
        elif stop.position == last:
            lead = cls._pick(leads["last"], seed)
        else:
            moves = leads["moves"].get(transport) or leads["moves"]["walk"]
            n = stop.travel_min_from_prev
            lead = fb.render_text(next(m["text"] for m in moves if n <= m["max"]), n=n)
        bodies = d["bodies"].get(stop.role) or d["bodies"]["default"]
        parts = [
            fb.render_text(
                cls._pick(bodies, seed),
                lead=lead,
                name=stop.place.name,
                what=cls.category_word(fb, stop.place.category_code),
            )
        ]
        prices = d["price_lines"]
        if stop.place.is_free or stop.est_price == 0:
            parts.append(str(prices["free"]))
        else:
            key = "estimated" if stop.place.price_is_estimated else "measured"
            parts.append(fb.render_text(prices[key], party=party, price=_won(stop.est_price)))
        # a tag is mentioned only when the purpose (or the user's picks) actually likes it
        liked = {t: w * tag_affinity[t] for t, w in stop.place.tags.items() if tag_affinity.get(t, 0.0) > 0}
        if liked:
            tag = max(liked, key=lambda t: liked[t])
            fact = (d.get("fact_lines") or {}).get(tag)
            parts.append(str(fact) if fact else fb.render_text(d["tag_line"], tag=tag))
        return " ".join(parts)

    @staticmethod
    def _reason(fb: Prompt, stop: StopResult, tag_affinity: Mapping[str, float]) -> str:
        phrases: dict[str, str] = fb.data["feature_phrases"]
        top = sorted(stop.score_breakdown.items(), key=lambda kv: -kv[1])
        picked: list[str] = []
        for feature, _ in top:
            key = "budget_free" if feature == "budget" and stop.place.price == 0 else feature
            if key in phrases:
                picked.append(phrases[key])
            if len(picked) == 2:
                break
        # highlight only tags the purpose likes — never a negative one such as a waiting-line tag
        liked = {t: w * tag_affinity[t] for t, w in stop.place.tags.items() if tag_affinity.get(t, 0.0) > 0}
        best_tag = max(liked, key=lambda t: liked[t], default=None)
        tail = fb.data["reason_tail"]
        ending = fb.render_text(tail["with_tag"], tag=best_tag) if best_tag else tail["default"]
        return " ".join([*picked, ending])

    @staticmethod
    def _tip(fb: Prompt, course: CourseResult, budget_total: int) -> str | None:
        tips = fb.data["tips"]
        left = budget_total - course.total_price
        if left < 0:
            return fb.render_text(tips["budget_over"], over=_won(-left))
        crowded = next((s for s in course.stops if s.congestion is not None and s.congestion >= 0.8), None)
        if crowded is not None:
            return fb.render_text(tips["crowded"], name=crowded.place.name)
        if left >= int(fb.data.get("budget_left_tip_min", 3000)):
            return fb.render_text(tips["budget_left"], left=_won(left))
        return str(tips["budget_tight"])

    # --- LLM ---------------------------------------------------------------------------------

    @staticmethod
    def facts(course: CourseResult, *, party_size: int, budget_total: int, transport: str) -> dict[str, Any]:
        """Structured facts only — the model never sees anything it could re-rank."""
        return {
            "party_size": party_size,
            "budget_total": budget_total,
            "total_price": course.total_price,
            "budget_left": budget_total - course.total_price,
            "travel_min": course.total_travel_min,
            "transport": transport,
            "stops": [
                {
                    "position": s.position,
                    "role": s.role,
                    "name": s.place.name,
                    "category": s.place.category_code,
                    "est_price": s.est_price,
                    "travel_min_from_prev": s.travel_min_from_prev,
                    "top_features": [
                        k for k, _ in sorted(s.score_breakdown.items(), key=lambda kv: -kv[1])[:2]
                    ],
                    "tags": sorted(s.place.tags, key=lambda t: -s.place.tags[t])[:4],
                    "congestion": s.congestion,
                }
                for s in course.stops
            ],
        }

    async def generate(
        self,
        course: CourseResult,
        *,
        party_size: int,
        budget_total: int,
        transport: str,
        use_llm: bool,
        tag_affinity: Mapping[str, float] | None = None,
    ) -> Narrative:
        fallback = self.template(
            course,
            party_size=party_size,
            budget_total=budget_total,
            transport=transport,
            tag_affinity=tag_affinity,
        )
        if not (use_llm and self._llm.available):
            return fallback
        prompt = self._prompts.get("course_narrative")
        facts = self.facts(course, party_size=party_size, budget_total=budget_total, transport=transport)
        rendered = prompt.render(facts=facts)
        try:
            data = await self._llm.complete_json(
                LLMRequest(
                    system=rendered.system,
                    messages=[LLMMessage(role="user", content=rendered.user)],
                    tier="smart",
                    max_tokens=rendered.max_tokens,
                    json_schema=rendered.output_schema,
                )
            )
            reasons = {int(s["position"]): str(s["reason"]) for s in data["stops"]}
            if set(reasons) != set(fallback.reasons):
                raise ValueError("stop positions do not match")
            return Narrative(str(data["summary"]), reasons, str(data.get("tip") or "") or None, prompt.ref)
        except (LLMError, KeyError, TypeError, ValueError) as exc:
            logger.warning("narrative.llm_failed", error=str(exc))
            return fallback

    async def stream(self, facts: dict[str, Any], fallback_text: str) -> AsyncIterator[str]:
        """Token stream for `GET /courses/{id}/narrative`; template text when no LLM is available."""
        if not self._llm.available:
            for line in fallback_text.splitlines(keepends=True):
                yield line
            return
        prompt = self._prompts.get("course_narrative_stream")
        rendered = prompt.render(facts=facts)
        request = LLMRequest(
            system=rendered.system,
            messages=[LLMMessage(role="user", content=rendered.user)],
            tier="smart",
            max_tokens=rendered.max_tokens,
        )
        emitted = False
        try:
            async for event in self._llm.stream(request):
                if event.type == "token" and event.text:
                    emitted = True
                    yield event.text
        except LLMError as exc:
            logger.warning("narrative.stream_failed", error=str(exc))
            if not emitted:
                for line in fallback_text.splitlines(keepends=True):
                    yield line
