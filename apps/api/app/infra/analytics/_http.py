"""Shared fire-and-forget HTTP sender for analytics adapters: never raises into the request path."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = httpx.Timeout(3.0, connect=2.0)


class HttpTrackerBase:
    name = "http"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self._client

    async def _post(self, url: str, *, json: Any, params: dict[str, str] | None = None) -> None:
        try:
            resp = await self.client.post(url, json=json, params=params)
            if resp.status_code >= 400:
                logger.warning("analytics %s rejected event: HTTP %s", self.name, resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning("analytics %s transport error: %s", self.name, exc)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
