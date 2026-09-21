from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.domain.models import GeoPoint
from app.services.directions_service import DirectionsService, TransitIndex

HONGDAE = GeoPoint(37.5563, 126.9236)


def _write(directory: Path) -> None:
    # entrance without a name -> the station name comes from the nearest station node
    (directory / "subway_entrances.tsv").write_text(
        "37.5560397\t126.9229218\t9\t\n37.5000000\t127.0000000\t1\t먼역\n", encoding="utf-8"
    )
    (directory / "stations.tsv").write_text("37.5571\t126.9245\t홍대입구\n", encoding="utf-8")
    (directory / "bus_stops.tsv").write_text("37.5567153\t126.9234040\t홍대입구역\t14015\n", encoding="utf-8")


def test_nearest_subway_exit_and_bus_stop(tmp_path: Path) -> None:
    _write(tmp_path)
    index = TransitIndex(tmp_path)

    subway = index.subway(HONGDAE)
    assert subway is not None
    assert subway["station"] == "홍대입구역"
    assert subway["exit"] == "9"
    assert subway["distance_m"] < 100
    assert subway["walk_min"] >= 1

    bus = index.bus(HONGDAE)
    assert bus is not None
    assert bus["name"] == "홍대입구역"
    assert bus["stop_no"] == "14015"


def test_no_hint_when_nothing_is_near(tmp_path: Path) -> None:
    _write(tmp_path)
    index = TransitIndex(tmp_path)
    jeju_hill = GeoPoint(33.3617, 126.5292)
    assert index.subway(jeju_hill) is None
    assert index.bus(jeju_hill) is None


def test_missing_files_mean_empty_index(tmp_path: Path) -> None:
    index = TransitIndex(tmp_path)
    assert index.subway(HONGDAE) is None
    assert index.bus(HONGDAE) is None


@pytest.mark.asyncio
async def test_walk_uses_router_geometry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/route/v1/foot/" in request.url.path
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distance": 420.4,
                        "duration": 318.0,
                        "geometry": {
                            "coordinates": [[126.9236, 37.5563], [126.9240, 37.5570], [126.9255, 37.5580]]
                        },
                        "legs": [{"distance": 420.4, "duration": 318.0}],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = DirectionsService(Settings(osrm_foot_url="https://router.test"), client)
        route = await service.walk([HONGDAE, GeoPoint(37.5580, 126.9255)])

    assert route["source"] == "osrm"
    assert route["coordinates"][0] == [37.5563, 126.9236]  # flipped to [lat, lng]
    assert route["legs"] == [{"distance_m": 420, "duration_min": 5}]


@pytest.mark.asyncio
async def test_walk_falls_back_to_straight_line_when_router_is_down() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = DirectionsService(Settings(osrm_foot_url="https://router-down.test"), client)
        route = await service.walk([HONGDAE, GeoPoint(37.5590, 126.9270)])

    assert route["source"] == "straight"
    assert len(route["coordinates"]) == 2
    assert route["legs"][0]["duration_min"] >= 1


@pytest.mark.asyncio
async def test_walk_without_router_configured() -> None:
    route = await DirectionsService(Settings(osrm_foot_url="")).walk([HONGDAE, GeoPoint(37.5590, 126.9270)])
    assert route["source"] == "straight"


def test_station_search_finds_neighbourhoods_that_are_not_regions(tmp_path: Path) -> None:
    _write(tmp_path)
    (tmp_path / "stations.tsv").write_text(
        "37.5088\t126.8912\t신도림\n37.5089\t126.8913\t신도림\n37.5081\t127.0116\t반포\n37.5034\t127.0050\t신반포\n",
        encoding="utf-8",
    )
    index = TransitIndex(tmp_path)

    found = index.search_stations("신도림")
    assert [s["name"] for s in found] == ["신도림역"]  # one entry although OSM has a node per line
    assert abs(found[0]["lat"] - 37.50885) < 1e-4

    assert [s["name"] for s in index.search_stations("반포")] == ["반포역", "신반포역"]  # prefix match first
    assert index.search_stations("반포역") == index.search_stations("반포")
    assert index.search_stations("   ") == [] and index.search_stations("없는역이름") == []
