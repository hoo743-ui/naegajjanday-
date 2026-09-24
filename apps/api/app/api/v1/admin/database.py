"""`/admin/database` — what the database holds, and the few housekeeping jobs an operator may run (docs/50).

Every write is in the audit log. Nothing here deletes a saved course, an account or a place: only never-saved
courses past their TTL (the same job as `cli purge-courses`), old page views, and backup files.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.engine import make_url

from app.api.v1.responses import PROBLEMS
from app.core import errors
from app.core.config import Settings
from app.core.deps import ContainerDep, SessionDep
from app.core.logging import get_logger
from app.infra.db.models import Course, Visit
from app.services import retention_service as retention
from app.services.audit import AuditDep

router = APIRouter(prefix="/database", tags=["admin:database"])
logger = get_logger(__name__)

TABLES = (
    ("user", "가입 계정"),
    ("refresh_token", "로그인 기록"),
    ("visit", "방문 기록"),
    ("recommendation_log", "코스 생성 기록"),
    ("course", "코스"),
    ("course_stop", "코스의 장소"),
    ("course_feedback", "코스 평가"),
    ("chat_session", "채팅"),
    ("place", "장소"),
    ("place_image", "장소 사진"),
    ("event", "행사 · 축제"),
    ("region", "지역"),
    ("audit_log", "관리자 작업 기록"),
    ("api_usage", "외부 API 사용량"),
)
KEEP_BACKUPS = 2
_backup_running = False


class TableCount(BaseModel):
    name: str
    label: str
    rows: int


class BackupFile(BaseModel):
    name: str
    size_bytes: int
    created_at: datetime


class DatabaseOverview(BaseModel):
    engine: str
    size_bytes: int | None = Field(description="SQLite 파일(+WAL) 크기. PostgreSQL 이면 없음")
    disk_free_bytes: int | None
    tables: list[TableCount]
    expired_unsaved_courses: int = Field(description="저장하지 않은 채 보관 기간이 지난 코스 (정리 대상)")
    unsaved_course_ttl_hours: int
    visits_total: int
    oldest_visit: datetime | None
    backups: list[BackupFile]
    backup_running: bool


class PurgeResult(BaseModel):
    matched: int
    deleted: int
    dry_run: bool


class PurgeVisitsIn(BaseModel):
    older_than_days: int = Field(ge=30, le=3650, description="이보다 오래된 방문 기록을 지운다 (최소 30일)")
    dry_run: bool = True


def _sqlite_path(settings: Settings) -> Path | None:
    if not settings.is_sqlite:
        return None
    database = make_url(settings.database_url).database
    return Path(database).resolve() if database and database != ":memory:" else None


def _backup_dir(settings: Settings) -> Path | None:
    path = _sqlite_path(settings)
    return path.parent / "backups" if path else None


def _backups(settings: Settings) -> list[BackupFile]:
    folder = _backup_dir(settings)
    if folder is None or not folder.exists():
        return []
    files = sorted(folder.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        BackupFile(
            name=p.name,
            size_bytes=p.stat().st_size,
            created_at=datetime.fromtimestamp(p.stat().st_mtime, UTC),
        )
        for p in files
    ]


@router.get("", response_model=DatabaseOverview, summary="DB 현황: 크기 · 테이블 행 수 · 정리 대상 · 백업")
async def overview(session: SessionDep, container: ContainerDep) -> DatabaseOverview:
    settings = container.settings
    tables = []
    for name, label in TABLES:
        try:
            rows = int(await session.scalar(text(f'SELECT count(*) FROM "{name}"')) or 0)
        except Exception:  # a table this deployment does not have yet
            await session.rollback()
            continue
        tables.append(TableCount(name=name, label=label, rows=rows))
    cutoff = datetime.now(UTC) - timedelta(hours=settings.unsaved_course_ttl_hours)
    expired = await session.scalar(
        select(func.count())
        .select_from(Course)
        .where(Course.status == "generated", Course.created_at < cutoff)
    )
    visits = await session.scalar(select(func.count()).select_from(Visit))
    oldest = await session.scalar(select(func.min(Visit.created_at)))
    path = _sqlite_path(settings)
    size = None
    free = None
    if path and path.exists():
        size = sum(p.stat().st_size for p in (path, Path(f"{path}-wal")) if p.exists())
        free = shutil.disk_usage(path.parent).free
    return DatabaseOverview(
        engine="sqlite" if settings.is_sqlite else "postgresql",
        size_bytes=size,
        disk_free_bytes=free,
        tables=tables,
        expired_unsaved_courses=int(expired or 0),
        unsaved_course_ttl_hours=settings.unsaved_course_ttl_hours,
        visits_total=int(visits or 0),
        oldest_visit=oldest,
        backups=_backups(settings),
        backup_running=_backup_running,
    )


@router.post("/purge-courses", response_model=PurgeResult, summary="저장하지 않은 오래된 코스 정리")
async def purge_courses(
    container: ContainerDep, audit: AuditDep, session: SessionDep, dry_run: bool = Query(default=True)
) -> PurgeResult:
    report = await retention.purge_unsaved_courses(container.db, container.settings, dry_run=dry_run)
    if not dry_run:
        audit.record("purge", "course", None, report.as_dict())
        await session.commit()
    return PurgeResult(matched=report.matched, deleted=report.deleted, dry_run=dry_run)


@router.post("/purge-visits", response_model=PurgeResult, summary="오래된 방문 기록 정리")
async def purge_visits(body: PurgeVisitsIn, session: SessionDep, audit: AuditDep) -> PurgeResult:
    cutoff = datetime.now(UTC) - timedelta(days=body.older_than_days)
    matched = int(
        await session.scalar(select(func.count()).select_from(Visit).where(Visit.created_at < cutoff)) or 0
    )
    deleted = 0
    if not body.dry_run and matched:
        result = await session.execute(delete(Visit).where(Visit.created_at < cutoff))
        deleted = int(getattr(result, "rowcount", 0) or 0)
        audit.record("purge", "visit", None, {"older_than_days": body.older_than_days, "deleted": deleted})
        await session.commit()
    return PurgeResult(matched=matched, deleted=deleted, dry_run=body.dry_run)


def _run_backup(source: Path, target: Path, keep: int) -> None:
    global _backup_running
    try:
        tmp = target.with_suffix(".partial")
        with sqlite3.connect(source) as src, sqlite3.connect(tmp) as dst:
            src.backup(dst, pages=4096)  # the backup API copies WAL too; a plain file copy would not
        tmp.replace(target)
        for old in sorted(target.parent.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
            old.unlink(missing_ok=True)
        logger.info("database.backup_done", file=target.name, size=target.stat().st_size)
    except Exception:
        logger.exception("database.backup_failed", file=target.name)
    finally:
        _backup_running = False


@router.post(
    "/backup",
    status_code=202,
    response_model=None,
    responses=PROBLEMS(409, 422),
    summary="백업 시작",
)
async def backup(
    container: ContainerDep, audit: AuditDep, session: SessionDep, tasks: BackgroundTasks
) -> None:
    """SQLite only: a consistent copy next to the database (`backups/`), the last two kept. Runs in the
    background — the overview says when it is done."""
    global _backup_running
    settings = container.settings
    path, folder = _sqlite_path(settings), _backup_dir(settings)
    if path is None or folder is None or not path.exists():
        raise errors.ValidationFailed("PostgreSQL 은 호스팅의 백업 기능(스냅샷)을 써 주세요.")
    if _backup_running:
        raise errors.Conflict("백업이 이미 진행 중이에요.")
    size = path.stat().st_size
    if shutil.disk_usage(folder.parent).free < size * 1.3:
        raise errors.ValidationFailed(
            "디스크 여유 공간이 부족해요. 오래된 백업을 지우거나 디스크를 늘려 주세요."
        )
    folder.mkdir(exist_ok=True)
    target = folder / f"naegajjanday-{datetime.now(UTC):%Y%m%d-%H%M%S}.db"
    _backup_running = True
    audit.record("backup", "database", target.name, {"size_bytes": size})
    await session.commit()
    tasks.add_task(asyncio.to_thread, _run_backup, path, target, KEEP_BACKUPS)


@router.delete("/backups/{name}", status_code=204, responses=PROBLEMS(404), summary="백업 파일 삭제")
async def delete_backup(name: str, container: ContainerDep, audit: AuditDep, session: SessionDep) -> None:
    folder = _backup_dir(container.settings)
    target = (folder / name).resolve() if folder else None
    if folder is None or target is None or target.parent != folder.resolve() or not target.is_file():
        raise errors.NotFound("그 백업 파일이 없어요.")
    target.unlink()
    audit.record("delete", "backup", name, {})
    await session.commit()
