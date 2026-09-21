"""Cache abstraction: Redis when REDIS_URL is set, otherwise a process-local TTL cache."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class Cache(Protocol):
    backend: str

    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_s: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> int: ...
    async def ping(self) -> bool: ...
    async def aclose(self) -> None: ...


class MemoryCache:
    backend = "memory"

    def __init__(self, max_items: int = 5000) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._max = max_items

    async def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, blob = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return json.loads(blob)

    async def set(self, key: str, value: Any, ttl_s: int) -> None:
        if len(self._data) >= self._max:
            now = time.monotonic()
            for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                self._data.pop(k, None)
            while len(self._data) >= self._max:
                self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + ttl_s, json.dumps(value, ensure_ascii=False, default=str))

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._data.pop(k, None)

    async def delete_prefix(self, prefix: str) -> int:
        victims = [k for k in self._data if k.startswith(prefix)]
        for k in victims:
            self._data.pop(k, None)
        return len(victims)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._data.clear()


class RedisCache:
    backend = "redis"

    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self.client: Redis = Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        blob = await self.client.get(key)
        return json.loads(blob) if blob is not None else None

    async def set(self, key: str, value: Any, ttl_s: int) -> None:
        await self.client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl_s)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self.client.delete(*keys)

    async def delete_prefix(self, prefix: str) -> int:
        count = 0
        async for key in self.client.scan_iter(match=f"{prefix}*", count=500):
            await self.client.delete(key)
            count += 1
        return count

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

    async def aclose(self) -> None:
        await self.client.aclose()


def build_cache(redis_url: str | None) -> Cache:
    if redis_url:
        return RedisCache(redis_url)
    logger.info("cache.memory_fallback", reason="REDIS_URL unset")
    return MemoryCache()
