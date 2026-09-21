"""PostHog capture API. https://posthog.com/docs/api/capture"""

from __future__ import annotations

from typing import Any

import httpx

from app.infra.analytics._http import HttpTrackerBase
from app.infra.analytics.base import AnalyticsEvent


class PostHogTracker(HttpTrackerBase):
    name = "posthog"

    def __init__(
        self, api_key: str, host: str = "https://us.i.posthog.com", *, client: httpx.AsyncClient | None = None
    ) -> None:
        if not api_key:
            raise ValueError("PostHog requires POSTHOG_API_KEY")
        super().__init__(client)
        self._api_key = api_key
        self._url = f"{host.rstrip('/')}/capture/"

    def build_payload(self, event: AnalyticsEvent) -> dict[str, Any]:
        return {
            "api_key": self._api_key,
            "event": event.name,
            "distinct_id": event.distinct_id,
            "properties": dict(event.properties),
            "timestamp": event.timestamp.isoformat(),
        }

    async def track(self, event: AnalyticsEvent) -> None:
        await self._post(self._url, json=self.build_payload(event))
