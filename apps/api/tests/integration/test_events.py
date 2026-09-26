"""`POST /v1/events` (docs/62): the catalog is the gate, the body is JSON whatever its content type."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from sqlalchemy import select

from app.api.v1.events import device_hash
from app.core.deps import Container
from app.infra.db.models import AppEvent
from tests.conftest import GENERATE_BODY

BROWSER = {
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Mobile/15E148",
    "content-type": "text/plain",
}


def beacon(device: str, *events: dict[str, Any]) -> bytes:
    return json.dumps({"device_id": device, "events": list(events)}, ensure_ascii=False).encode()


async def stored(container: Container, device: str) -> list[AppEvent]:
    async with container.db.sessionmaker() as session:
        hashed = device_hash(container.settings.jwt_secret, device)
        return list((await session.scalars(select(AppEvent).where(AppEvent.device == hashed))).all())


class TestCollect:
    async def test_a_beacon_batch_is_stored_with_whitelisted_props_only(
        self, client: httpx.AsyncClient, container: Container, user_headers: dict[str, str]
    ) -> None:
        course = "0b7f6c1e-8d7a-4c1e-9d2a-3f5e6a7b8c9d"
        now_ms = time.time() * 1000
        body = beacon(
            "dev-aaaa-1111",
            {
                "name": "course_saved",
                "course_id": course,
                "props": {"price": 38000},
                "ts": now_ms,
                "path": "/course/x?y=1",
            },
            {
                "name": "course_option_text_parsed",
                "props": {"course_id": course, "length": 17, "matched": 1, "text": "영화 보고 싶어"},
                "ts": now_ms,
            },
            {
                "name": "directions_opened",
                "course_id": "not-a-uuid",
                "props": {"position": 2, "from": "prev"},
            },
            {"name": "share_clicked", "path": "/admin/users"},  # admin screens are not product use
        )
        resp = await client.post("/v1/events", content=body, headers={**BROWSER, **user_headers})
        assert resp.status_code == 202, resp.text
        assert resp.json() == {"accepted": 3, "dropped": 1}

        rows = {r.name: r for r in await stored(container, "dev-aaaa-1111")}
        assert set(rows) == {"course_saved", "course_option_text_parsed", "directions_opened"}
        saved = rows["course_saved"]
        assert (saved.course_id, saved.path, saved.props, saved.user_id is not None) == (
            course,
            "/course/x",
            {"price": 38000},
            True,
        )
        parsed = rows["course_option_text_parsed"]
        assert parsed.course_id == course and parsed.props == {"length": 17, "matched": 1}
        assert rows["directions_opened"].course_id is None

    async def test_unknown_names_are_refused(self, client: httpx.AsyncClient, container: Container) -> None:
        only_unknown = beacon("dev-bbbb-2222", {"name": "password_typed"}, {"name": "x" * 60})
        resp = await client.post("/v1/events", content=only_unknown, headers=BROWSER)
        assert (resp.status_code, resp.json()["code"]) == (422, "VALIDATION_ERROR")

        mixed = beacon(
            "dev-bbbb-2222", {"name": "password_typed"}, {"name": "plan_started", "props": {"entry": "nav"}}
        )
        resp = await client.post("/v1/events", content=mixed, headers=BROWSER)
        assert resp.status_code == 202 and resp.json()["unknown"] == ["password_typed"]
        assert [r.name for r in await stored(container, "dev-bbbb-2222")] == ["plan_started"]

        broken = await client.post("/v1/events", content=b"{not json", headers=BROWSER)
        assert broken.status_code == 422
        empty = await client.post("/v1/events", content=beacon("dev-bbbb-2222"), headers=BROWSER)
        assert empty.status_code == 422

    async def test_do_not_track_bots_and_size(self, client: httpx.AsyncClient, container: Container) -> None:
        body = beacon("dev-cccc-3333", {"name": "plan_started", "props": {"entry": "nav"}})
        assert (
            await client.post("/v1/events", content=body, headers={**BROWSER, "DNT": "1"})
        ).status_code == 204
        assert (
            await client.post("/v1/events", content=body, headers={**BROWSER, "Sec-GPC": "1"})
        ).status_code == 204
        bot = {**BROWSER, "user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}
        assert (await client.post("/v1/events", content=body, headers=bot)).status_code == 204
        assert await stored(container, "dev-cccc-3333") == []

        huge = beacon(
            "dev-cccc-3333", *({"name": "plan_started", "props": {"entry": "n" * 60}} for _ in range(50))
        )
        huge += b" " * (33 * 1024 - len(huge))
        assert (await client.post("/v1/events", content=huge, headers=BROWSER)).status_code == 413
        too_many = beacon("dev-cccc-3333", *({"name": "plan_started"} for _ in range(51)))
        assert (await client.post("/v1/events", content=too_many, headers=BROWSER)).status_code == 422

    async def test_rate_limited_per_device(self, client: httpx.AsyncClient, container: Container) -> None:
        settings = container.settings
        before = settings.rl_events_device
        settings.rl_events_device = "2/60"
        try:
            body = beacon("dev-dddd-4444", {"name": "plan_started", "props": {"entry": "nav"}})
            codes = [
                (await client.post("/v1/events", content=body, headers=BROWSER)).status_code for _ in range(3)
            ]
            assert codes == [202, 202, 429]
        finally:
            settings.rl_events_device = before


class TestUsageMetrics:
    async def test_a_shared_course_is_a_used_course(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str], user_headers: dict[str, str]
    ) -> None:
        path = "/v1/admin/analytics/usage-metrics"
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=user_headers)).status_code == 403
        before = (await client.get(path, headers=admin_headers)).json()["north_star"][-1]

        made = await client.post("/v1/courses/generate", json={**GENERATE_BODY, "budget_total": 47000})
        assert made.status_code == 200, made.text
        course = made.json()["courses"][0]["id"]
        body = beacon(
            "dev-eeee-5555",
            {"name": "course_generated", "course_id": course, "props": {"stops": 4}},
            {"name": "stop_swapped", "course_id": course, "props": {"position": 1, "strategy": "cheaper"}},
            {"name": "share_clicked", "course_id": course, "props": {"method": "clipboard"}},
        )
        assert (await client.post("/v1/events", content=body, headers=BROWSER)).status_code == 202

        m = (await client.get(path, headers=admin_headers, params={"days": 7})).json()
        week = m["north_star"][-1]
        assert len(m["north_star"]) == 8 and m["days"] == 7 and m["collecting_since"]
        assert week["generated"] == before["generated"] + 1
        assert week["used"] == before["used"] + 1 and week["signals"]["shared"] >= 1
        assert m["with_events"]["count"] >= 1 and sum(c["swaps"] for c in m["swap_by_category"]) >= 1
        assert any(e["name"] == "share_clicked" and e["devices"] >= 1 for e in m["events"])
