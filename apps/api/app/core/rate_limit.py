"""Sliding-window rate limiter (keys rl:{scope}:{id}): Redis sorted set, or an in-memory deque."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_s: int  # seconds until the window frees a slot

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_s),
        }


class RateLimiter(Protocol):
    async def hit(self, scope: str, identity: str, limit: int, window_s: int) -> RateLimitResult: ...
    async def reset(self) -> None: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, scope: str, identity: str, limit: int, window_s: int) -> RateLimitResult:
        now = time.monotonic()
        q = self._hits[f"rl:{scope}:{identity}"]
        while q and q[0] <= now - window_s:
            q.popleft()
        if len(q) >= limit:
            return RateLimitResult(False, limit, 0, max(1, int(q[0] + window_s - now) + 1))
        q.append(now)
        return RateLimitResult(True, limit, limit - len(q), int(q[0] + window_s - now) + 1)

    async def reset(self) -> None:
        self._hits.clear()


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._redis: Redis = Redis.from_url(url, decode_responses=True)

    async def hit(self, scope: str, identity: str, limit: int, window_s: int) -> RateLimitResult:
        key = f"rl:{scope}:{identity}:{window_s}"
        now = time.time()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, now - window_s)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            _, count, oldest = await pipe.execute()
        oldest_ts = oldest[0][1] if oldest else now
        if count >= limit:
            return RateLimitResult(False, limit, 0, max(1, int(oldest_ts + window_s - now) + 1))
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
            pipe.expire(key, window_s + 1)
            await pipe.execute()
        return RateLimitResult(True, limit, limit - count - 1, int(oldest_ts + window_s - now) + 1)

    async def reset(self) -> None:
        async for key in self._redis.scan_iter(match="rl:*", count=500):
            await self._redis.delete(key)


def build_rate_limiter(redis_url: str | None) -> RateLimiter:
    return RedisRateLimiter(redis_url) if redis_url else MemoryRateLimiter()
