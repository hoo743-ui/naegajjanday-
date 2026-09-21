"""Mixpanel ingestion API (/track). https://developer.mixpanel.com/reference/track-event"""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.infra.analytics._http import HttpTrackerBase
from app.infra.analytics.base import AnalyticsEvent

TRACK_URL = "https://api.mixpanel.com/track"


class MixpanelTracker(HttpTrackerBase):
    name = "mixpanel"

    def __init__(self, token: str, *, client: httpx.AsyncClient | None = None) -> None:
        if not token:
            raise ValueError("Mixpanel requires MIXPANEL_TOKEN")
        super().__init__(client)
        self._token = token

    def build_payload(self, event: AnalyticsEvent) -> list[dict[str, Any]]:
        insert_id = hashlib.sha1(
            f"{event.name}|{event.distinct_id}|{event.timestamp.isoformat()}".encode()
        ).hexdigest()
        return [
            {
                "event": event.name,
                "properties": {
                    **event.properties,
                    "token": self._token,
                    "distinct_id": event.distinct_id,
                    "time": int(event.timestamp.timestamp()),
                    "$insert_id": insert_id,
                },
            }
        ]

    async def track(self, event: AnalyticsEvent) -> None:
        await self._post(TRACK_URL, json=self.build_payload(event), params={"verbose": "1"})
