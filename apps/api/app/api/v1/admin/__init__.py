"""`/admin/*` — every route requires role ∈ {admin, operator}; every write goes to `audit_log`."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.admin import (
    analytics,
    banners,
    events,
    ingestion,
    places,
    regions,
    scoring,
    system,
    templates,
)
from app.api.v1.responses import PROBLEMS
from app.core.deps import require_admin

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)], responses=PROBLEMS(401, 403))
for module in (places, events, banners, regions, scoring, templates, ingestion, analytics, system):
    router.include_router(module.router)
