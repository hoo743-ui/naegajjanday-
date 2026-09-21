"""Hard rule #1: opening a new region needs DATA only — a regions.json row and a places file.

This test writes both into a tmp dir, runs the same loader/pipeline the CLI uses, and generates a
course for the new region. No Python module knows the slug `jeju-aewol`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx

from app.core.config import API_ROOT
from app.core.deps import Container
from app.infra.ingestion.config_loader import load_config
from app.services.ingestion_runner import ingest

SLUG = "jeju-aewol"
CENTER = (33.4630, 126.3100)
HOURS = [{"dow": [0, 1, 2, 3, 4, 5, 6], "open": "10:00", "close": "22:00"}]


def _place(i: int, name: str, category: str, menus: list[int] | None, **extra: object) -> dict[str, object]:
    return {
        "external_id": f"aewol-{i:03d}",
        "name": name,
        "category": category,
        "lat": CENTER[0] + ((i % 5) - 2) * 0.0012,
        "lng": CENTER[1] + ((i % 3) - 1) * 0.0015,
        "address": "제주 제주시 애월읍 (테스트)",
        "is_free": menus is None and "price_per_person" not in extra,
        "menus": [
            {"name": f"메뉴{j}", "price": p, "is_signature": j == 0} for j, p in enumerate(menus or [])
        ],
        "opening_hours": [] if menus is None else HOURS,
        "rating": {"avg": 4.0 + (i % 5) / 10, "count": 40 + i * 7},
        "sentiment": {"score": 0.5, "count": 30, "aspects": {"taste": 0.7, "mood": 0.8}},
        "tags": {"뷰맛집": 0.8} if i % 2 else {"조용한": 0.7},
        **extra,
    }


def write_region_data(root: Path) -> Path:
    regions = {
        "regions": [
            {"slug": "jeju", "name": "제주특별자치도", "level": 1, "parent": None, "center_lat": 33.4996,
             "center_lng": 126.5312, "radius_m": 40000, "status": "active"},
            {"slug": SLUG, "name": "애월", "level": 3, "parent": "jeju", "center_lat": CENTER[0],
             "center_lng": CENTER[1], "radius_m": 1500, "status": "active", "search_keywords": ["애월 맛집"]},
        ]
    }  # fmt: skip
    (root / "regions.json").write_text(json.dumps(regions, ensure_ascii=False), encoding="utf-8")
    meals = ["food.korean", "food.noodle", "food.japanese", "food.western", "food.asian", "food.snack"]
    cafes = ["cafe.coffee", "cafe.roastery", "cafe.view", "cafe.book", "cafe.tea"]
    sights = ["attraction.park", "attraction.street", "attraction.market", "attraction.landmark"]
    places = [
        _place(i, f"테스트 식당 {i}", c, [9000 + i * 800, 11000 + i * 800, 13000])
        for i, c in enumerate(meals)
    ]
    places += [
        _place(10 + i, f"테스트 카페 {i}", c, [4000 + i * 300, 4500, 5500]) for i, c in enumerate(cafes)
    ]
    places += [_place(20 + i, f"테스트 산책로 {i}", c, None) for i, c in enumerate(sights)]
    places_file = root / "places" / f"{SLUG}.json"
    places_file.parent.mkdir()
    places_file.write_text(
        json.dumps({"region": SLUG, "places": places}, ensure_ascii=False), encoding="utf-8"
    )
    return places_file


async def test_new_region_needs_only_data(
    client: httpx.AsyncClient, container: Container, tmp_path: Path
) -> None:
    body = {"region": SLUG, "purpose": "date", "party_size": 2, "budget_total": 40000,
            "start_at": "2026-09-20T18:00:00+09:00"}  # fmt: skip
    before = await client.post("/v1/courses/generate", json=body)
    assert (before.status_code, before.json()["code"]) == (404, "REGION_NOT_FOUND")

    places_file = write_region_data(tmp_path)
    async with container.db.sessionmaker() as session:  # == `python -m app.cli seed-config --dir <tmp>`
        report = await load_config(session, tmp_path)
        await session.commit()
    assert report.regions == 2 and report.purposes == 0  # only a region row was added
    # == `python -m app.cli ingest --provider file --path <file>`
    slug, ingested = await ingest(
        container.db, container.settings, provider_name="file", region_slug=None, path=places_file
    )
    assert (slug, ingested.created, ingested.failed) == (SLUG, 15, 0)
    await container.cache.delete_prefix("region:list")

    listed = (await client.get("/v1/meta/regions", params={"q": "애월"})).json()["items"]
    assert (
        listed[0]["slug"] == SLUG and listed[0]["place_count"] == 15 and listed[0]["parent"]["slug"] == "jeju"
    )

    after = await client.post("/v1/courses/generate", json=body)
    assert after.status_code == 200, after.text
    course = after.json()["courses"][0]
    assert [s["role"] for s in course["stops"]] == ["MEAL", "CAFE", "ATTRACTION"]
    assert all(s["place"]["name"].startswith("테스트") for s in course["stops"])
    assert course["totals"]["price"] == sum(s["est_price"] for s in course["stops"]) <= 42000

    again = await ingest(
        container.db, container.settings, provider_name="file", region_slug=None, path=places_file
    )
    assert (again[1].created, again[1].skipped) == (0, 15)  # unchanged content hash → skipped


def test_no_region_or_place_names_are_hardcoded_in_python() -> None:
    seed = json.loads((API_ROOT / "data" / "seed" / "regions.json").read_text(encoding="utf-8"))
    needles = [r["slug"] for r in seed["regions"] if r["level"] == 3] + [
        "홍대입구",
        "경의선숲길",
        "짠이네 국수",
    ]
    offenders = [
        f"{path.relative_to(API_ROOT)}:{lineno}: {needle}"
        for path in (API_ROOT / "app").rglob("*.py")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for needle in needles
        if needle in line and "examples=" not in line  # OpenAPI example values are documentation
    ]
    assert offenders == []


def test_cli_is_wired() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli", "--help"], cwd=API_ROOT, capture_output=True, check=False
    )
    out = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0 and all(
        cmd in out for cmd in ("db", "seed-config", "ingest", "create-admin")
    )
