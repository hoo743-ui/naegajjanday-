"""An operator uploads a real photo of a place: the only way past the 3 % that public data covers."""

from __future__ import annotations

import base64

import httpx

# a valid 1x1 PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


async def _some_place(client: httpx.AsyncClient, headers: dict[str, str]) -> dict:
    rows = (await client.get("/v1/admin/places", params={"limit": 1}, headers=headers)).json()["items"]
    return rows[0]


class TestPlacePhotos:
    async def test_a_real_photo_becomes_the_cover_and_is_served(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        place = await _some_place(client, admin_headers)
        resp = await client.post(
            f"/v1/admin/places/{place['id']}/photos",
            headers=admin_headers,
            files={"file": ("shop.png", PNG, "image/png")},
            data={"make_cover": "true"},
        )
        assert resp.status_code == 200, resp.text
        detail = (await client.get(f"/v1/places/{place['id']}")).json()
        cover = detail["thumbnail_url"]
        assert cover and "/uploads/" in cover and cover.endswith(".png")
        assert detail["images"][0] == cover
        served = await client.get(cover[cover.index("/uploads/") :])
        assert served.status_code == 200 and served.content == PNG

        # the same picture again is stored once and listed once
        await client.post(
            f"/v1/admin/places/{place['id']}/photos",
            headers=admin_headers,
            files={"file": ("again.png", PNG, "image/png")},
        )
        again = (await client.get(f"/v1/places/{place['id']}")).json()
        assert again["images"].count(cover) == 1

    async def test_what_is_not_a_picture_is_refused_whatever_it_is_called(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        place = await _some_place(client, admin_headers)
        resp = await client.post(
            f"/v1/admin/places/{place['id']}/photos",
            headers=admin_headers,
            files={"file": ("photo.jpg", b"<script>alert(1)</script>", "image/jpeg")},
        )
        assert resp.status_code == 422

    async def test_only_operators_may_upload(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        place = await _some_place(client, admin_headers)
        resp = await client.post(
            f"/v1/admin/places/{place['id']}/photos", files={"file": ("shop.png", PNG, "image/png")}
        )
        assert resp.status_code in (401, 403)
