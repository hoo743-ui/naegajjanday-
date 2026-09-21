"""GA4 Measurement Protocol. https://developers.google.com/analytics/devguides/collection/protocol/ga4"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.infra.analytics._http import HttpTrackerBase
from app.infra.analytics.base import AnalyticsEvent

COLLECT_URL = "https://www.google-analytics.com/mp/collect"
_NAME_RE = re.compile(r"[^A-Za-z0-9_]")
MAX_PARAMS = 25


def _param_value(value: Any) -> str | int | float:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    return str(value)[:100]


class GA4Tracker(HttpTrackerBase):
    name = "ga4"

    def __init__(
        self, measurement_id: str, api_secret: str, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if not measurement_id or not api_secret:
            raise ValueError("GA4 requires GA4_MEASUREMENT_ID and GA4_API_SECRET")
        super().__init__(client)
        self._params = {"measurement_id": measurement_id, "api_secret": api_secret}

    def build_payload(self, event: AnalyticsEvent) -> dict[str, Any]:
        params = {
            _NAME_RE.sub("_", k)[:40]: _param_value(v) for k, v in list(event.properties.items())[:MAX_PARAMS]
        }
        params.setdefault("engagement_time_msec", 1)
        return {
            "client_id": event.distinct_id,
            "timestamp_micros": int(event.timestamp.timestamp() * 1_000_000),
            "events": [{"name": _NAME_RE.sub("_", event.name)[:40], "params": params}],
        }

    async def track(self, event: AnalyticsEvent) -> None:
        await self._post(COLLECT_URL, json=self.build_payload(event), params=self._params)
