from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    attractions,
    auth,
    chat,
    courses,
    directions,
    events,
    extras,
    me,
    media,
    meta,
    performances,
    places,
    stays,
    visits,
)
from app.api.v1.admin import router as admin_router

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(courses.router)
api_router.include_router(extras.router)
api_router.include_router(places.router)
api_router.include_router(attractions.router)
api_router.include_router(stays.router)
api_router.include_router(performances.router)
api_router.include_router(directions.router)
api_router.include_router(media.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(chat.router)
api_router.include_router(visits.router)
api_router.include_router(events.router)
api_router.include_router(admin_router)
