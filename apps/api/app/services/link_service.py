"""Where to read more about a place or festival — straight to the right page, not a search list (docs/44).

Order of the links:
1. official — the place's own site: the festival standard data (`event.booking_url`) or TourAPI
   `detailCommon2.homepage` (the contentid we already store).
2. place_page — the Kakao Map page of *that* place (reviews · photos · hours), found with the official
   Kakao Local API by name + coordinates. Only when the name and the position agree; otherwise a
   Kakao Map search, marked `exact=False`.
3. blog — a Naver blog search for "<동네> <이름> 후기" (a link to their search page, nothing fetched).
4. route — Kakao Map directions (to the matched place id when we have one).

Nothing is scraped: two official APIs, and plain links to other sites' own pages. Results are cached
for a week (misses for an hour) so a sheet opening costs at most two API calls.
"""

from __future__ import annotations

import asyncio
import html
import re
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors
from app.core.cache import Cache
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.media import name_similarity
from app.infra.db.models import Event, Place, PlaceSource
from app.infra.ingestion.dedupe import distance_m

logger = get_logger(__name__)

LinkKind = Literal["official", "place_page", "blog", "route"]
KAKAO_KEYWORD = "https://dapi.kakao.com/v2/local/search/keyword.json"
TOURAPI_COMMON = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"
TTL_HIT_S = 7 * 24 * 3600
TTL_MISS_S = 3600
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_PORTALS = {"korean.visitkorea.or.kr", "www.visitkorea.or.kr", "visitkorea.or.kr", "english.visitkorea.or.kr"}
_URL = re.compile(r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+)", re.IGNORECASE)


class ExternalLink(BaseModel):
    kind: LinkKind
    label: str
    url: str
    source: str
    exact: bool  # True = that place's own page; False = a search result page


class PlaceLinks(BaseModel):
    items: list[ExternalLink]


# ── pure helpers (tested) ────────────────────────────────────────────────────────


def clean_url(value: str | None) -> str | None:
    """TourAPI `homepage` is HTML (`<a href="…">…</a>`) or bare text. Only http(s) survives."""
    text = html.unescape((value or "").strip())
    if not text:
        return None
    m = _HREF.search(text) or _URL.search(text)
    url = (m.group(1) if m else text).strip()
    if url.lower().startswith("www."):
        url = "http://" + url
    if not re.match(r"^https?://[^\s/]+\.[^\s]+", url, re.IGNORECASE):
        return None
    # 관광 포털의 첫 화면은 그 장소의 홈페이지가 아니다 (DMZ 축제의 "홈페이지"가 포털 첫 화면이었다)
    parts = urlsplit(url)
    if parts.hostname in _PORTALS and parts.path.strip("/") == "" and not parts.query:
        return None
    return url


def pick_kakao(docs: list[dict[str, Any]], name: str, lat: float, lng: float) -> dict[str, Any] | None:
    """The Kakao place that is this place: similar name AND close. A same-name shop 1 km away is not it."""
    best: tuple[float, dict[str, Any]] | None = None
    for d in docs:
        try:
            dist = distance_m(lat, lng, float(d["y"]), float(d["x"]))
        except (KeyError, TypeError, ValueError):
            continue
        sim = name_similarity(name, str(d.get("place_name") or ""))
        if (sim >= 0.6 and dist <= 250) or (sim >= 0.4 and dist <= 60):
            score = sim - dist / 1000
            if best is None or score > best[0]:
                best = (score, d)
    return best[1] if best else None


def area_of(address: str | None) -> str:
    """ "서울특별시 성동구 성수동2가 …" → "성동구" (a blog search needs the district, not the city)."""
    parts = (address or "").split()
    return parts[1] if len(parts) > 1 else (parts[0] if parts else "")


def build_links(
    *,
    name: str,
    lat: float,
    lng: float,
    address: str | None,
    official: str | None,
    kakao: dict[str, Any] | None,
    festival: bool,
) -> list[ExternalLink]:
    items: list[ExternalLink] = []
    if official:
        items.append(
            ExternalLink(
                kind="official",
                label="공식 홈페이지",
                url=official,
                source=(urlsplit(official).hostname or "").removeprefix("www."),  # 어디로 가는지 미리 보이게
                exact=True,
            )
        )
    area = area_of(address)
    if kakao and kakao.get("place_url"):
        page = str(kakao["place_url"]).replace("http://", "https://", 1)
        items.append(
            ExternalLink(
                kind="place_page", label="카카오맵 후기 · 사진", url=page, source="카카오맵", exact=True
            )
        )
    else:
        q = quote(f"{area} {name}".strip())
        items.append(
            ExternalLink(
                kind="place_page",
                label="카카오맵에서 찾기",
                url=f"https://map.kakao.com/?q={q}",
                source="카카오맵",
                exact=False,
            )
        )
    blog_q = f"{name} 후기" if festival else f"{area} {name} 후기".strip()
    items.append(
        ExternalLink(
            kind="blog",
            label="블로그 후기",
            url=f"https://search.naver.com/search.naver?where=blog&query={quote(blog_q)}",
            source="네이버 블로그",
            exact=False,
        )
    )
    to = (
        f"https://map.kakao.com/link/to/{kakao['id']}"
        if kakao and kakao.get("id")
        else f"https://map.kakao.com/link/to/{quote(name)},{lat},{lng}"
    )
    items.append(
        ExternalLink(kind="route", label="여기까지 길찾기", url=to, source="카카오맵", exact=bool(kakao))
    )
    return items


# ── the service ──────────────────────────────────────────────────────────────────


class LinkService:
    def __init__(
        self, session: AsyncSession, settings: Settings, cache: Cache, client: httpx.AsyncClient | None = None
    ):
        self.session = session
        self.settings = settings
        self.cache = cache
        self._client = client

    async def for_place(self, public_id: str) -> PlaceLinks:
        key = f"links:place:{public_id}"
        if (hit := await self.cache.get(key)) is not None:
            return PlaceLinks.model_validate(hit)
        place = (
            await self.session.execute(select(Place).where(Place.public_id == public_id))
        ).scalar_one_or_none()
        if place is None:
            raise errors.PlaceNotFound()
        content_id = (
            await self.session.execute(
                select(PlaceSource.external_id).where(
                    PlaceSource.place_id == place.id, PlaceSource.provider == "tourapi"
                )
            )
        ).scalar()
        return await self._resolve(
            key,
            name=place.name,
            lat=place.lat,
            lng=place.lng,
            address=place.road_address or place.address,
            official=None,
            content_id=content_id,
            festival=False,
        )

    async def for_event(self, public_id: str) -> PlaceLinks:
        key = f"links:event:{public_id}"
        if (hit := await self.cache.get(key)) is not None:
            return PlaceLinks.model_validate(hit)
        event = (
            await self.session.execute(select(Event).where(Event.public_id == public_id))
        ).scalar_one_or_none()
        if event is None:
            raise errors.NotFound("행사를 찾을 수 없어요")
        return await self._resolve(
            key,
            name=event.title,
            lat=event.lat,
            lng=event.lng,
            address=event.address,
            official=clean_url(event.booking_url),
            content_id=event.external_id if event.provider == "tourapi" else None,
            festival=True,
        )

    async def _resolve(
        self,
        key: str,
        *,
        name: str,
        lat: float,
        lng: float,
        address: str | None,
        official: str | None,
        content_id: str | None,
        festival: bool,
    ) -> PlaceLinks:
        async def none() -> tuple[None, bool]:
            return None, True

        async with self._http() as client:
            # 두 API 를 동시에 부른다 (차례로 부르면 시트가 열리는 데 2~3초 걸렸다)
            (homepage, ok_home), (kakao, ok_kakao) = await asyncio.gather(
                self._tourapi_homepage(client, content_id) if official is None and content_id else none(),
                # 축제는 장소가 아니라 행사라 카카오 장소와 맞추지 않는다 (같은 이름의 가게가 잡힌다)
                none() if festival else self._kakao_place(client, name, lat, lng),
            )
        official = official or homepage
        complete = ok_home and ok_kakao
        links = PlaceLinks(
            items=build_links(
                name=name,
                lat=lat,
                lng=lng,
                address=address,
                official=official,
                kakao=kakao,
                festival=festival,
            )
        )
        await self.cache.set(key, links.model_dump(), TTL_HIT_S if complete else TTL_MISS_S)
        return links

    def _http(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        # 테스트가 넘긴 클라이언트는 닫지 않는다
        return nullcontext(self._client) if self._client else httpx.AsyncClient(timeout=4.0)

    async def _tourapi_homepage(self, client: httpx.AsyncClient, content_id: str) -> tuple[str | None, bool]:
        if not self.settings.tourapi_service_key:
            return None, True
        params = {
            "serviceKey": self.settings.tourapi_service_key,
            "MobileOS": "ETC",
            "MobileApp": "naegajjanday",
            "_type": "json",
            "contentId": content_id,
        }
        try:
            r = await client.get(TOURAPI_COMMON, params=params)
            r.raise_for_status()
            items = ((r.json().get("response") or {}).get("body") or {}).get("items") or {}
            item = (items.get("item") or [{}])[0] if isinstance(items, dict) else {}
            return clean_url(item.get("homepage")), True
        except (httpx.HTTPError, ValueError, AttributeError, IndexError) as e:
            logger.warning("links.tourapi_failed", content_id=content_id, error=str(e)[:120])
            return None, False

    async def _kakao_place(
        self, client: httpx.AsyncClient, name: str, lat: float, lng: float
    ) -> tuple[dict[str, Any] | None, bool]:
        if not self.settings.kakao_rest_api_key:
            return None, True
        params = {
            "query": name,
            "x": f"{lng:.7f}",
            "y": f"{lat:.7f}",
            "radius": "400",
            "sort": "distance",
            "size": "5",
        }
        try:
            r = await client.get(
                KAKAO_KEYWORD,
                params=params,
                headers={"Authorization": f"KakaoAK {self.settings.kakao_rest_api_key}"},
            )
            r.raise_for_status()
            return pick_kakao(r.json().get("documents") or [], name, lat, lng), True
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("links.kakao_failed", error=str(e)[:120])
            return None, False
