"""Server-Sent Events helpers."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

HEARTBEAT_INTERVAL_S = 15.0  # CloudFront drops origin connections that stay silent for 60 s
HEARTBEAT = ": ping\n\n"  # SSE comment line — ignored by EventSource clients
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def with_heartbeat(
    source: AsyncIterator[str], interval_s: float = HEARTBEAT_INTERVAL_S
) -> AsyncIterator[str]:
    """Pass `source` through, emitting a comment line whenever it is silent for `interval_s`."""
    iterator = source.__aiter__()
    pending: asyncio.Future[str] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval_s)
            if not done:
                yield HEARTBEAT
                continue
            task, pending = pending, None
            try:
                item = task.result()
            except StopAsyncIteration:
                return
            yield item
    finally:
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
