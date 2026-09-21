from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.v1.health import Readiness, check_components
from app.core.deps import ContainerDep, SessionDep
from app.infra.db.models import Place, SearchOutbox
from app.schemas import admin as dto
from app.services.audit import AuditDep

router = APIRouter(tags=["admin:system"])


@router.get("/system/health", response_model=Readiness)
async def system_health(container: ContainerDep) -> Readiness:
    components = await check_components(container)
    ok = all(c.status in {"ok", "disabled"} for c in components.values())
    return Readiness(status="ready" if ok else "degraded", components=components)


@router.post("/cache/invalidate", response_model=dto.CacheInvalidateResult)
async def invalidate_cache(
    container: ContainerDep,
    session: SessionDep,
    audit: AuditDep,
    body: dto.CacheInvalidateRequest | None = None,
) -> dto.CacheInvalidateResult:
    prefixes = (body or dto.CacheInvalidateRequest()).prefixes
    deleted = 0
    for prefix in prefixes:
        deleted += await container.cache.delete_prefix(prefix)
    audit.record("cache.invalidate", "cache", None, {"prefixes": prefixes, "deleted": deleted})
    await session.commit()
    return dto.CacheInvalidateResult(deleted=deleted)


@router.post(
    "/search/reindex",
    response_model=dto.ReindexResult,
    status_code=202,
    summary="모든 장소를 search_outbox 에 넣어 워커가 재색인하게 한다",
)
async def reindex(container: ContainerDep, session: SessionDep, audit: AuditDep) -> dto.ReindexResult:
    ids = (await session.scalars(select(Place.id))).all()
    session.add_all(SearchOutbox(entity="place", entity_id=i, op="upsert") for i in ids)
    audit.record("search.reindex", "search", None, {"enqueued": len(ids)})
    await session.commit()
    return dto.ReindexResult(
        enqueued=len(ids),
        search_backend=container.search.backend if container.search else "sql-fallback (ES_URL unset)",
    )
