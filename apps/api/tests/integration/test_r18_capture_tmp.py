"""TEMP (R18 criterion ①): fingerprint fixed requests; run before and after the change and diff."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from app.domain.recommendation import ticketed
from tests.conftest import GENERATE_BODY

OUT = Path(os.environ.get("R18_OUT", "r18.json"))

CASES = {
    "date": {**GENERATE_BODY},
    "family_lunch": {**GENERATE_BODY, "purpose": "family", "party_size": 3, "budget_total": 120000,
                     "start_at": "2026-09-26T11:00:00+09:00"},
    "family_night": {**GENERATE_BODY, "purpose": "family", "party_size": 3, "budget_total": 90000,
                     "start_at": "2026-09-26T22:00:00+09:00"},
    "family_parents": {**GENERATE_BODY, "purpose": "family", "scene": "parents", "party_size": 4,
                       "budget_total": 160000, "start_at": "2026-09-26T12:00:00+09:00"},
    "family_adults": {**GENERATE_BODY, "purpose": "family", "scene": "adults", "party_size": 4,
                      "budget_total": 160000, "start_at": "2026-09-26T18:00:00+09:00"},
    "friends_bar": {**GENERATE_BODY, "purpose": "friends", "party_size": 4, "budget_total": 160000,
                    "extras": ["BAR"], "start_at": "2026-09-26T18:00:00+09:00"},
    "seongsu_family": {**GENERATE_BODY, "region": "seoul-seongsu", "purpose": "family", "party_size": 4,
                       "budget_total": 200000, "start_at": "2026-09-27T10:30:00+09:00"},
    "seomyeon_date": {**GENERATE_BODY, "region": "busan-seomyeon", "budget_total": 70000},
}  # fmt: skip


def fp(course: dict) -> dict:
    return {
        "stops": [
            [s["place"]["name"], s["role"], s["est_price"], s["arrive_at"], s.get("reason_short")]
            for s in course["stops"]
        ],
        "total": course["totals"]["price"],
        "warnings": sorted(w["code"] for w in course["warnings"]),
    }


@pytest.mark.skipif("R18_OUT" not in os.environ, reason="capture only")
async def test_capture(client: httpx.AsyncClient, tmp_path: Path) -> None:
    out: dict = {}
    for name, body in CASES.items():
        r = await client.post("/v1/courses/generate", json=body)
        out[name] = [fp(c) for c in r.json()["courses"]] if r.status_code == 200 else r.status_code
    # a pinned ticketed venue for a family of three (the assumption: two adults, one child)
    base = {**CASES["family_lunch"], "alternatives": 0}
    first = (await client.post("/v1/courses/generate", json=base)).json()["courses"][0]
    stop = next(s for s in first["stops"] if s["role"] not in ("MEAL", "CAFE", "DESSERT", "BAR"))
    p = stop["place"]
    data = {
        "inner_roles": ["MEAL", "CAFE", "DESSERT", "BAR"],
        "venues": [{"key": "t", "name": p["name"], "gate": [p["lat"], p["lng"]], "radius_m": 200,
                    "admission": {"adult": 52000, "child": 43000, "as_of": "2026-09", "basis": "공식"}}],
    }  # fmt: skip
    f = tmp_path / "t.json"
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    wrapped = ticketed.ticketed_venues.__wrapped__  # type: ignore[attr-defined]
    old = wrapped.__defaults__
    wrapped.__defaults__ = (f,)
    ticketed.ticketed_venues.cache_clear()
    try:
        r = await client.post(
            "/v1/courses/generate", json={**base, "budget_total": 400000, "keep_place_ids": [p["id"]]}
        )
        out["pinned_venue"] = [fp(c) for c in r.json()["courses"]] if r.status_code == 200 else r.text
    finally:
        wrapped.__defaults__ = old
        ticketed.ticketed_venues.cache_clear()
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
