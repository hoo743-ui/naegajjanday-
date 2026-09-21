"""Service construction for the API layer (FastAPI `Depends`) and for the chat tool executor."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Container, ContainerDep, SessionDep
from app.services.auth_service import AuthService
from app.services.course_service import CourseService
from app.services.meta_service import MetaService
from app.services.narrative_service import NarrativeService
from app.services.place_service import PlaceService


def build_course_service(container: Container, session: AsyncSession) -> CourseService:
    return CourseService(
        settings=container.settings,
        session=session,
        cache=container.cache,
        narrative=NarrativeService(container.prompts, container.llm),
        tracker=container.tracker,
        travel_provider=container.travel,
    )


def course_service(container: ContainerDep, session: SessionDep) -> CourseService:
    return build_course_service(container, session)


def place_service(container: ContainerDep, session: SessionDep) -> PlaceService:
    return PlaceService(container.settings, session, container.search)


def meta_service(container: ContainerDep, session: SessionDep) -> MetaService:
    return MetaService(session, container.cache)


def auth_service(container: ContainerDep, session: SessionDep) -> AuthService:
    return AuthService(container.settings, session, container.cache)


CourseServiceDep = Annotated[CourseService, Depends(course_service)]
PlaceServiceDep = Annotated[PlaceService, Depends(place_service)]
MetaServiceDep = Annotated[MetaService, Depends(meta_service)]
AuthServiceDep = Annotated[AuthService, Depends(auth_service)]
