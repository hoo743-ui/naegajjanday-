from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import func, select

from app.core.deps import Container
from app.infra.db.models import AuditLog
from tests.conftest import GENERATE_BODY

ADMIN_GETS = [
    "/v1/admin/places",
    "/v1/admin/events",
    "/v1/admin/banners",
    "/v1/admin/regions",
    "/v1/admin/scoring-profiles/date",
    "/v1/admin/templates",
    "/v1/admin/purposes/date/tag-affinities",
    "/v1/admin/ingestion/jobs",
    "/v1/admin/analytics/recommendations",
    "/v1/admin/analytics/places/top",
    "/v1/admin/system/health",
]


class TestAccessControl:
    @pytest.mark.parametrize("path", ADMIN_GETS)
    async def test_rejects_anonymous_and_plain_users(
        self, client: httpx.AsyncClient, user_headers: dict[str, str], path: str
    ) -> None:
        anon = await client.get(path)
        assert (anon.status_code, anon.json()["code"]) == (401, "UNAUTHORIZED")
        user = await client.get(path, headers=user_headers)
        assert (user.status_code, user.json()["code"]) == (403, "FORBIDDEN")

    async def test_writes_are_rejected_too(
        self, client: httpx.AsyncClient, user_headers: dict[str, str]
    ) -> None:
        assert (await client.post("/v1/admin/cache/invalidate")).status_code == 401
        assert (await client.post("/v1/admin/cache/invalidate", headers=user_headers)).status_code == 403
        assert (
            await client.put("/v1/admin/scoring-profiles/date", headers=user_headers, json={})
        ).status_code == 403

    @pytest.mark.parametrize("path", ADMIN_GETS)
    async def test_admin_can_read(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str], path: str
    ) -> None:
        assert (await client.get(path, headers=admin_headers)).status_code == 200

    async def test_role_comes_from_the_database_not_the_token(
        self, client: httpx.AsyncClient, container: Container
    ) -> None:
        from app.core import security
        from app.repositories.user_repo import SqlUserRepository

        async with container.db.sessionmaker() as s:
            user = await SqlUserRepository(s).create(email="forged@example.com", nickname="f", role="user")
            await s.commit()
        forged, _ = security.create_access_token(
            container.settings, user_public_id=user.public_id, role="admin"
        )
        resp = await client.get("/v1/admin/places", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 403


class TestModeration:
    async def test_suggest_approve_edit_revisions_and_audit(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        user_headers: dict[str, str],
        container: Container,
    ) -> None:
        body = {"region": "seoul-hongdae", "name": "승인 대기 분식", "category": "food.snack", "lat": 37.5570, "lng": 126.9240,
                "price_per_person": 6000}  # fmt: skip
        place_id = (await client.post("/v1/places/suggest", json=body, headers=user_headers)).json()["id"]
        queue = (
            await client.get("/v1/admin/places", params={"status": "pending"}, headers=admin_headers)
        ).json()
        assert place_id in [p["id"] for p in queue["items"]]

        approved = await client.post(
            f"/v1/admin/places/{place_id}/approve", headers=admin_headers, json={"note": "확인"}
        )
        assert approved.status_code == 200 and approved.json()["status"] == "approved"
        assert (await client.get(f"/v1/places/{place_id}")).status_code == 200

        patched = await client.patch(f"/v1/admin/places/{place_id}", headers=admin_headers,
                                     json={"price_per_person": 7000, "tags": {"가성비": 0.9}})  # fmt: skip
        assert patched.json()["price_per_person"] == 7000
        assert "가성비" in (await client.get(f"/v1/places/{place_id}")).json()["tags"]

        revisions = (
            await client.get(f"/v1/admin/places/{place_id}/revisions", headers=admin_headers)
        ).json()["items"]
        assert [r["action"] for r in revisions] == ["edit", "approve", "create"]
        assert (
            revisions[0]["before"]["price_per_person"] == 6000
            and revisions[0]["after"]["price_per_person"] == 7000
        )

        rejected = await client.post(f"/v1/admin/places/{place_id}/reject", headers=admin_headers)
        assert rejected.json()["status"] == "rejected"
        assert (await client.get(f"/v1/places/{place_id}")).status_code == 404
        async with container.db.sessionmaker() as s:
            n = await s.scalar(select(func.count(AuditLog.id)).where(AuditLog.entity_id == place_id))
        assert n == 3  # approve, edit, reject — every admin write is audited

    async def test_create_attraction_merge_and_bulk_approve(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        def body(name: str) -> dict[str, object]:
            return {"region": "seoul-seongsu", "category": "attraction.landmark", "name": name,
                    "lat": 37.5450, "lng": 127.0560, "is_free": True}  # fmt: skip

        a = (
            await client.post("/v1/admin/places", headers=admin_headers, json=body("성수 샘플 조형물"))
        ).json()
        b = (
            await client.post("/v1/admin/places", headers=admin_headers, json=body("성수 샘플 조형물 (중복)"))
        ).json()
        assert a["status"] == "approved" and a["sources"] == ["admin"]
        merged = await client.post(
            f"/v1/admin/places/{a['id']}/merge", headers=admin_headers, json={"duplicate_id": b["id"]}
        )
        assert merged.status_code == 200
        hidden = (
            await client.get("/v1/admin/places", params={"status": "hidden"}, headers=admin_headers)
        ).json()
        assert b["id"] in [p["id"] for p in hidden["items"]]
        bulk = await client.post(
            "/v1/admin/places/bulk-approve", headers=admin_headers, json={"ids": [b["id"], "missing"]}
        )
        assert bulk.json() == {"updated": 1, "not_found": ["missing"]}

    async def test_import_json_upload_runs_the_file_pipeline(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        payload = {"places": [{"external_id": "upload-1", "name": "업로드 샘플 공원", "category": "attraction.park",
                               "lat": 35.1580, "lng": 129.0605, "is_free": True}]}  # fmt: skip
        files = {"file": ("parks.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")}
        resp = await client.post(
            "/v1/admin/places/import", headers=admin_headers, files=files, data={"region": "busan-seomyeon"}
        )
        assert resp.status_code == 200, resp.text
        job = resp.json()
        assert (job["status"], job["provider"], job["created_count"], job["failed_count"]) == (
            "succeeded",
            "file",
            1,
            0,
        )
        jobs = (await client.get("/v1/admin/ingestion/jobs", headers=admin_headers)).json()["items"]
        assert job["id"] in [j["id"] for j in jobs]
        bad = {"file": ("x.txt", b"nope", "text/plain")}
        assert (
            await client.post(
                "/v1/admin/places/import", headers=admin_headers, files=bad, data={"region": "x"}
            )
        ).status_code == 422


class TestConfig:
    async def test_scoring_profile_update_bumps_version_and_changes_results(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        current = (await client.get("/v1/admin/scoring-profiles/date", headers=admin_headers)).json()
        bad = {**current, "weights": {**current["weights"], "budget": 0.9}}
        del bad["purpose"], bad["version"]
        assert (
            await client.put("/v1/admin/scoring-profiles/date", headers=admin_headers, json=bad)
        ).status_code == 422

        body = {
            "weights": current["weights"],
            "params": {**current["params"], "lambda_travel": 0.02},
            "is_active": True,
        }
        updated = await client.put("/v1/admin/scoring-profiles/date", headers=admin_headers, json=body)
        assert updated.status_code == 200 and updated.json()["version"] == current["version"] + 1
        generated = await client.post("/v1/courses/generate", json=GENERATE_BODY)  # cache was invalidated
        assert generated.json()["meta"]["scoring_profile"] == f"date@v{current['version'] + 1}"
        # 관리자 화면은 가중치만 보낸다 — 그때 params(스타일·변형 설정)가 통째로 지워지면 안 된다
        weights_only = await client.put(
            "/v1/admin/scoring-profiles/date", headers=admin_headers, json={"weights": current["weights"]}
        )
        assert weights_only.status_code == 200
        assert weights_only.json()["params"]["lambda_travel"] == 0.02

    async def test_templates_and_affinities(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        slots = [
            {"course_role": "DESSERT", "budget_share": 0.6},
            {"course_role": "NIGHTVIEW", "budget_share": 0.4},
        ]
        template = {"code": "friends-night-snack", "purpose": "friends", "name": "야식", "time_band": "evening",
                    "min_budget_per_person": 5000, "slots": slots}  # fmt: skip
        created = await client.post("/v1/admin/templates", headers=admin_headers, json=template)
        assert created.status_code == 201 and len(created.json()["slots"]) == 2
        assert (
            await client.post("/v1/admin/templates", headers=admin_headers, json=template)
        ).status_code == 409
        broken = {"slots": [{"course_role": "DESSERT", "budget_share": 0.2}]}
        assert (
            await client.patch("/v1/admin/templates/friends-night-snack", headers=admin_headers, json=broken)
        ).status_code == 422
        off = await client.patch(
            "/v1/admin/templates/friends-night-snack", headers=admin_headers, json={"is_active": False}
        )
        assert off.json()["is_active"] is False

        aff = (await client.get("/v1/admin/purposes/date/tag-affinities", headers=admin_headers)).json()[
            "affinities"
        ]
        aff["포토존"] = 0.9
        put = await client.put(
            "/v1/admin/purposes/date/tag-affinities", headers=admin_headers, json={"affinities": aff}
        )
        assert put.json()["affinities"]["포토존"] == 0.9
        unknown = await client.put(
            "/v1/admin/purposes/date/tag-affinities",
            headers=admin_headers,
            json={"affinities": {"없는태그": 1}},
        )
        assert unknown.status_code == 422

    async def test_events_and_banners_crud(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        event = {"region": "seoul-hongdae", "title": "관리자 샘플 전시", "category": "culture.exhibition", "lat": 37.5571,
                 "lng": 126.9246, "starts_on": "2026-09-01", "ends_on": "2026-10-01", "is_free": True}  # fmt: skip
        created = await client.post("/v1/admin/events", headers=admin_headers, json=event)
        assert created.status_code == 201
        public = await client.get(
            "/v1/events", params={"region": "seoul-hongdae", "from": "2026-09-10", "to": "2026-09-10"}
        )
        assert "관리자 샘플 전시" in [e["title"] for e in public.json()["items"]]
        event_id = created.json()["id"]
        ended = await client.patch(
            f"/v1/admin/events/{event_id}", headers=admin_headers, json={"status": "ended"}
        )
        assert ended.json()["status"] == "ended"
        assert (await client.delete(f"/v1/admin/events/{event_id}", headers=admin_headers)).status_code == 204

        banner = {
            "title": "가을 데이트",
            "image_url": "https://cdn.example.com/b.png",
            "placement": "home",
            "region": "seoul-hongdae",
        }
        bid = (await client.post("/v1/admin/banners", headers=admin_headers, json=banner)).json()["id"]
        shown = (
            await client.get("/v1/meta/banners", params={"placement": "home", "region": "seoul-hongdae"})
        ).json()
        assert [b["id"] for b in shown["items"]] == [bid]
        assert (await client.get("/v1/meta/banners", params={"region": "busan-seomyeon"})).json()[
            "items"
        ] == []
        assert (await client.delete(f"/v1/admin/banners/{bid}", headers=admin_headers)).status_code == 204


class TestOpsAndAnalytics:
    async def test_unimplemented_endpoints_say_so(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        users = await client.get("/v1/admin/analytics/users", headers=admin_headers)
        assert (users.status_code, users.json()["code"]) == (501, "NOT_IMPLEMENTED")
        presign = await client.post("/v1/admin/uploads/presign", headers=admin_headers,
                                    json={"filename": "a.png", "content_type": "image/png"})  # fmt: skip
        assert (presign.status_code, presign.json()["code"]) == (501, "NOT_IMPLEMENTED")

    async def test_recommendation_stats_are_computed_from_logs(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        await client.post("/v1/courses/generate", json={**GENERATE_BODY, "budget_total": 52000})
        stats = (await client.get("/v1/admin/analytics/recommendations", headers=admin_headers)).json()
        assert stats["generated"] >= 1 and stats["latency_p95_ms"] >= stats["latency_p50_ms"] >= 0
        assert {"region": "seoul-hongdae", "purpose": "date"} in [
            {"region": c["region"], "purpose": c["purpose"]} for c in stats["heatmap"]
        ]
        top = (await client.get("/v1/admin/analytics/places/top", headers=admin_headers)).json()["items"]
        assert top and top[0]["recommend_count"] >= 1

    async def test_ingestion_job_requires_known_api_provider(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        bad = await client.post(
            "/v1/admin/ingestion/jobs",
            headers=admin_headers,
            json={"provider": "scraper", "region": "seoul-hongdae"},
        )
        assert bad.status_code == 422
        queued = await client.post(
            "/v1/admin/regions/seoul-hongdae/collect",
            headers=admin_headers,
            json={"providers": ["kakao_local"]},
        )
        assert (
            queued.status_code == 202 and queued.json()[0]["status"] == "queued"
        )  # no broker → stays queued
        assert (
            await client.post(
                f"/v1/admin/ingestion/jobs/{queued.json()[0]['id']}/retry", headers=admin_headers
            )
        ).status_code == 409

    async def test_cache_invalidate_and_reindex(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        await client.get("/v1/meta/regions")
        cleared = await client.post("/v1/admin/cache/invalidate", headers=admin_headers)
        assert cleared.status_code == 200 and cleared.json()["deleted"] >= 1
        reindex = await client.post("/v1/admin/search/reindex", headers=admin_headers)
        assert reindex.status_code == 202 and reindex.json()["enqueued"] >= 114
