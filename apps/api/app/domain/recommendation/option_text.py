"""한 줄 말 → 코스 옵션 (docs/59 #2).

The result page takes one line — "애플스토어 들렀다가 영화 보고 싶어" — and turns it into the options a course
request already has: extras (BAR · MOVIE · BASEBALL), conditions (rain) and a must-visit place (errand).
No LLM (no key is configured, and the same words must always mean the same thing): the phrases live in
data/recommendation/option_phrases.json, this module only reads them.

What it never does: invent a place. The errand is a *query* — the name as the user wrote it; the API looks
it up with the same search the "꼭 들를 곳" box uses, and the page shows what it found before anything is
generated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

PHRASES_PATH = Path(__file__).resolve().parents[3] / "data" / "recommendation" / "option_phrases.json"

When = Literal["before", "after"]


@dataclass(frozen=True)
class OptionRule:
    key: str
    kind: Literal["extra", "condition"]
    label: str
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class ErrandRules:
    verbs: re.Pattern[str]
    max_tokens: int
    skip: frozenset[str]
    stop: tuple[re.Pattern[str], ...]
    clause_endings: tuple[str, ...]
    particles: tuple[str, ...]
    after_markers: re.Pattern[str]
    min_length: int


@dataclass(frozen=True)
class PhraseRules:
    options: tuple[OptionRule, ...]
    declined: re.Pattern[str]
    errand: ErrandRules


@dataclass(frozen=True)
class ErrandAsk:
    query: str
    when: When


@dataclass
class ParsedOptions:
    extras: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    # said "빼고 · 말고": the page takes these off the request
    declined: list[str] = field(default_factory=list)
    errand: ErrandAsk | None = None
    # what was read, in the order it was said: (option key or "ERRAND", the words it came from)
    matched: list[tuple[str, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.extras or self.conditions or self.declined or self.errand)


def _compile(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


@lru_cache(maxsize=1)
def phrase_rules(path: Path = PHRASES_PATH) -> PhraseRules:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    options = tuple(
        OptionRule(
            key=str(o["key"]),
            kind="condition" if o["kind"] == "condition" else "extra",
            label=str(o["label"]),
            patterns=_compile([str(p) for p in o["patterns"]]),
        )
        for o in data["options"]
    )
    e = data["errand"]
    errand = ErrandRules(
        verbs=re.compile("|".join(f"(?:{v})" for v in e["verbs"])),
        max_tokens=int(e["max_tokens"]),
        skip=frozenset(str(s) for s in e["skip"]),
        stop=tuple(re.compile(f"^(?:{s})$") for s in e["stop"]),
        clause_endings=tuple(str(c) for c in e["clause_endings"]),
        # longest first: "에서" before "에"
        particles=tuple(sorted((str(p) for p in e["particles"]), key=len, reverse=True)),
        after_markers=re.compile("|".join(f"(?:{m})" for m in e["after_markers"])),
        min_length=int(e["min_length"]),
    )
    return PhraseRules(options=options, declined=re.compile(str(data["declined"])), errand=errand)


def _normalize(text: str) -> str:
    # punctuation separates clauses the way a space does; "~" and "!" carry no meaning here
    return re.sub(r"\s+", " ", re.sub(r"[,.!?~·/]+", " ", text)).strip()


def _strip_particle(token: str, particles: tuple[str, ...]) -> str:
    for p in particles:
        if token.endswith(p) and len(token) > len(p) + 1:
            return token[: -len(p)]
    return token


def _option_at(rules: PhraseRules, text: str) -> list[tuple[int, int, OptionRule]]:
    """Every option phrase in the text: (start, end, rule), in reading order."""
    hits: list[tuple[int, int, OptionRule]] = []
    for rule in rules.options:
        for pattern in rule.patterns:
            hits.extend((m.start(), m.end(), rule) for m in pattern.finditer(text))
    return sorted(hits, key=lambda h: (h[0], -h[1]))


def _names_an_option(rules: PhraseRules, words: str) -> bool:
    return any(p.search(words) for rule in rules.options for p in rule.patterns)


def _errand(rules: PhraseRules, text: str) -> tuple[ErrandAsk, str] | None:
    """The first "<place> 들렀다가 …" in the text. Walks back from the verb over the words before it:
    adverbs between the place and the verb are skipped, and the name ends at a word that is not a name
    (오늘 · 끝나고 · 먹고 …) or after `max_tokens` words."""
    er = rules.errand
    for verb in er.verbs.finditer(text):
        tokens = text[: verb.start()].split()
        while tokens and tokens[-1] in er.skip:
            tokens.pop()
        said: list[str] = []
        for token in reversed(tokens):
            if len(said) >= er.max_tokens or any(s.match(token) for s in er.stop):
                break
            if said and token.endswith(er.clause_endings):
                break  # "밥 먹고 다이소 들렀다가": 먹고 ends the clause before the place
            said.insert(0, token)
        name = [*said[:-1], _strip_particle(said[-1], er.particles)] if said else []
        query = " ".join(name).strip()
        if len(query.replace(" ", "")) < er.min_length or _names_an_option(rules, query):
            continue  # "야구장 갔다가" is the baseball option, not a shop to find
        when: When = "after" if er.after_markers.search(text[: verb.start()]) else "before"
        return ErrandAsk(query=query, when=when), " ".join([*said, verb.group()])
    return None


def parse_options(text: str, rules: PhraseRules | None = None) -> ParsedOptions:
    """One line of Korean → the course request's options. Deterministic; unknown words are ignored."""
    rules = rules or phrase_rules()
    line = _normalize(text)
    out = ParsedOptions()
    if not line:
        return out
    errand = _errand(rules, line)
    for start, end, rule in _option_at(rules, line):
        if rule.key in out.extras or rule.key in out.conditions or rule.key in out.declined:
            continue
        words = line[start:end]
        if rules.declined.match(line[end:]):
            out.declined.append(rule.key)
            out.matched.append((rule.key, words))
            continue
        (out.extras if rule.kind == "extra" else out.conditions).append(rule.key)
        out.matched.append((rule.key, words))
    if errand:
        out.errand = errand[0]
        out.matched.append(("ERRAND", errand[1]))
    return out


LAST_CHOICE_FIELDS = (
    "purpose",
    "scene",
    "party_size",
    "budget_total",
    "transport",
    "move_style",
    "pace",
    "wishes",
)


def last_choices(body: dict[str, Any], known_extras: Iterable[str]) -> dict[str, Any]:
    """A signed-in user's last course request → what the wizard starts from next time (docs/59 #2).
    Only the four essentials' answers and the taste; never the day's own facts (date, rain, a shop to drop by,
    places to exclude). The neighbourhood only when it was one plain neighbourhood (not a station, a campus,
    a shop or several areas — those were that day's)."""
    out: dict[str, Any] = {k: body[k] for k in LAST_CHOICE_FIELDS if body.get(k) not in (None, "", [])}
    several = len(body.get("regions") or []) > 1
    plain = not (body.get("origin") or body.get("anchor") or body.get("errand") or several)
    if plain and isinstance(body.get("region"), str) and body["region"]:
        out["region"] = body["region"]
    known = set(known_extras)
    out["extras"] = [e for e in dict.fromkeys(body.get("extras") or []) if e in known]
    return out


def option_label(key: str, rules: PhraseRules | None = None) -> str:
    rules = rules or phrase_rules()
    return next((r.label for r in rules.options if r.key == key), key)
