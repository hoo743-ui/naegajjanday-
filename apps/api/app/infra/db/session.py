from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import Connection, event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateColumn

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    url = settings.database_url
    if url.startswith("sqlite"):
        kwargs: dict[str, object] = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        engine = create_async_engine(url, echo=settings.db_echo, **kwargs)

        @event.listens_for(engine.sync_engine, "connect")
        def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_async_engine(url, echo=settings.db_echo, pool_size=10, max_overflow=20, pool_pre_ping=True)


def _sqlite_add_missing(conn: Connection) -> None:
    """`create_all` never alters existing tables: add columns / indexes that are newer than the file."""
    from app.infra.db.base import Base

    inspector = inspect(conn)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {CreateColumn(column).compile(dialect=conn.dialect)}"
            conn.execute(text(ddl))
        for index in table.indexes:
            index.create(conn, checkfirst=True)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(settings)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Unit of work: commit on success, rollback on error."""
        async with self.sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        from app.infra.db import models  # noqa: F401  (register mappers)
        from app.infra.db.base import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if self.dialect == "sqlite":  # no Alembic on SQLite: bring an older file up to date
                await conn.run_sync(_sqlite_add_missing)

    async def dispose(self) -> None:
        await self.engine.dispose()
