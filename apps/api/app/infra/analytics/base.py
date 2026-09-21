"""Server-side product analytics abstraction. Default is a no-op tracker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    name: str  # e.g. "course_generated", "course_saved", "stop_swapped"
    distinct_id: str  # user public_id or anonymous client id — never email/IP
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class EventTracker(Protocol):
    name: str

    async def track(self, event: AnalyticsEvent) -> None:
        """Must never raise into the request path; log and swallow transport errors."""
        ...

    async def aclose(self) -> None: ...


class NoopTracker:
    name = "none"

    async def track(self, event: AnalyticsEvent) -> None:
        return None

    async def aclose(self) -> None:
        return None
