"""Search gateway. Optional at runtime: when ES_URL is unset `build_search()` returns None and the
place service falls back to SQL LIKE search.

Production is Amazon OpenSearch Service, which the official `elasticsearch` 8.x client refuses to
talk to, so the implementation uses `opensearch-py` (async). Services only see `PlaceSearch`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from opensearchpy import AsyncOpenSearch, NotFoundError

from app.core.config import Settings
from app.infra.search.index import PLACES_INDEX, index_name


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str | None = None
    region_slug: str | None = None
    roles: tuple[str, ...] = ()
    max_price: int | None = None
    lat: float | None = None
    lng: float | None = None
    radius_m: float | None = None
    sort: str = "relevance"
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SearchHit:
    public_id: str
    distance_m: float | None


class PlaceSearch(Protocol):
    backend: str

    async def ping(self) -> bool: ...
    async def aclose(self) -> None: ...
    async def ensure_index(self, version: int | None = None) -> str: ...
    async def swap_alias(self, new_index: str) -> None: ...
    async def bulk(self, operations: list[dict[str, Any]], index: str | None = None) -> dict[str, Any]: ...
    async def search(self, query: SearchQuery) -> list[SearchHit]: ...
    async def autocomplete(self, q: str, limit: int = 8) -> list[str]: ...


def build_query(query: SearchQuery) -> dict[str, Any]:
    """Query DSL shared by OpenSearch and Elasticsearch."""
    must: list[dict[str, Any]] = []
    filters: list[dict[str, Any]] = [{"term": {"status": "approved"}}]
    if query.q:
        must.append(
            {
                "multi_match": {
                    "query": query.q,
                    "fields": ["name^3", "name.autocomplete", "address", "tags^2"],
                }
            }
        )
    if query.region_slug:
        filters.append({"term": {"region_slug": query.region_slug}})
    if query.roles:
        filters.append({"terms": {"course_role": list(query.roles)}})
    if query.max_price is not None:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"is_free": True}},
                        {"range": {"price_per_person": {"lte": query.max_price}}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    location = {"lat": query.lat, "lon": query.lng}
    has_geo = query.lat is not None and query.lng is not None
    if has_geo and query.radius_m:
        filters.append({"geo_distance": {"distance": f"{int(query.radius_m)}m", "location": location}})
    sort: list[Any] = ["_score"]
    if query.sort == "distance" and has_geo:
        sort = [{"_geo_distance": {"location": location, "order": "asc", "unit": "m"}}]
    elif query.sort == "rating":
        sort = [{"bayes_rating": "desc"}, "_score"]
    elif query.sort == "price":
        sort = [{"price_per_person": {"order": "asc", "missing": "_first"}}]
    elif query.sort == "popularity":
        sort = [{"popularity": "desc"}, "_score"]
    body: dict[str, Any] = {
        "query": {"bool": {"must": must or [{"match_all": {}}], "filter": filters}},
        "sort": sort,
        "from": query.offset,
        "size": query.limit,
        "_source": ["public_id"],
    }
    if has_geo and query.sort != "distance":
        body["script_fields"] = {
            "distance_m": {
                "script": {
                    "source": "doc['location'].arcDistance(params.lat, params.lon)",
                    "params": location,
                }
            }
        }
    return body


class OpenSearchPlaceSearch:
    backend = "opensearch"

    def __init__(self, client: AsyncOpenSearch, alias: str) -> None:
        self._os = client
        self._alias = alias

    async def ping(self) -> bool:
        try:
            return bool(await self._os.ping())
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._os.close()

    # --- index lifecycle: new versioned index, then atomic alias swap (zero downtime) ---------

    async def ensure_index(self, version: int | None = None) -> str:
        name = index_name(version) if version else index_name()
        if not await self._os.indices.exists(index=name):
            await self._os.indices.create(index=name, body=PLACES_INDEX)
        if not await self._os.indices.exists_alias(name=self._alias):
            await self._os.indices.put_alias(index=name, name=self._alias)
        return name

    async def swap_alias(self, new_index: str) -> None:
        actions: list[dict[str, Any]] = []
        try:
            current = await self._os.indices.get_alias(name=self._alias)
            actions += [{"remove": {"index": idx, "alias": self._alias}} for idx in current]
        except NotFoundError:
            pass
        actions.append({"add": {"index": new_index, "alias": self._alias}})
        await self._os.indices.update_aliases(body={"actions": actions})

    async def bulk(self, operations: list[dict[str, Any]], index: str | None = None) -> dict[str, Any]:
        resp = await self._os.bulk(body=operations, index=index or self._alias)
        return dict(resp)

    # --- queries -----------------------------------------------------------------------------

    async def search(self, query: SearchQuery) -> list[SearchHit]:
        resp = await self._os.search(index=self._alias, body=build_query(query))
        hits: list[SearchHit] = []
        for h in resp["hits"]["hits"]:
            dist = None
            if query.sort == "distance" and h.get("sort"):
                dist = float(h["sort"][0])
            elif "fields" in h and "distance_m" in h["fields"]:
                dist = float(h["fields"]["distance_m"][0])
            hits.append(SearchHit(public_id=h["_source"]["public_id"], distance_m=dist))
        return hits

    async def autocomplete(self, q: str, limit: int = 8) -> list[str]:
        body = {
            "query": {
                "bool": {
                    "must": [{"match": {"name.autocomplete": {"query": q, "operator": "and"}}}],
                    "filter": [{"term": {"status": "approved"}}],
                }
            },
            "sort": [{"popularity": "desc"}, "_score"],
            "size": limit,
            "_source": ["public_id"],
        }
        resp = await self._os.search(index=self._alias, body=body)
        return [h["_source"]["public_id"] for h in resp["hits"]["hits"]]


def build_search(settings: Settings) -> PlaceSearch | None:
    if not settings.es_url:
        return None
    kwargs: dict[str, Any] = {
        "hosts": [settings.es_url],
        "timeout": 2,
        "use_ssl": settings.es_url.startswith("https"),
        "verify_certs": settings.es_verify_certs,
    }
    if settings.es_username and settings.es_password:  # OpenSearch fine-grained access control
        kwargs["http_auth"] = (settings.es_username, settings.es_password)
    return OpenSearchPlaceSearch(AsyncOpenSearch(**kwargs), settings.es_index_alias)
