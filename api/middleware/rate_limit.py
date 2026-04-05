"""Rate limiting middleware with Redis-backed sliding window.

Uses Redis (e.g. ElastiCache) in production for distributed rate limiting
across multiple ECS tasks.  Falls back to an in-memory token bucket when
Redis is unavailable or in development mode.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings

logger = logging.getLogger(__name__)

_RATE_LIMIT = settings.rate_limit_per_minute
_WINDOW_SECONDS = 60

# ---------------------------------------------------------------------------
# Redis backend (preferred in production)
# ---------------------------------------------------------------------------

_redis: Any = None


def _get_redis():
    """Lazy-init a Redis connection from settings.redis_url."""
    global _redis
    if _redis is not None:
        return _redis
    redis_url = getattr(settings, "redis_url", "")
    if not redis_url:
        return None
    try:
        import redis as _redis_lib  # type: ignore[import-untyped]

        _redis = _redis_lib.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        _redis.ping()
        logger.info("rate-limiter connected to Redis at %s", redis_url)
        return _redis
    except Exception:
        logger.warning("rate-limiter Redis unavailable, using in-memory fallback")
        _redis = None
        return None


def _redis_consume(client_ip: str) -> tuple[bool, int]:
    """Sliding-window counter via Redis INCR + EXPIRE.

    Returns (allowed, remaining).
    """
    r = _get_redis()
    if r is None:
        raise RuntimeError("no redis")
    key = f"rl:{client_ip}"
    try:
        current = r.incr(key)
        if current == 1:
            r.expire(key, _WINDOW_SECONDS)
        ttl = r.ttl(key)
        if ttl == -1:
            r.expire(key, _WINDOW_SECONDS)
        remaining = max(0, _RATE_LIMIT - current)
        return current <= _RATE_LIMIT, remaining
    except Exception as exc:
        raise RuntimeError("redis error") from exc


# ---------------------------------------------------------------------------
# In-memory fallback (single-instance / dev)
# ---------------------------------------------------------------------------


class _TokenBucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self) -> None:
        self.tokens: float = _RATE_LIMIT
        self.last_refill: float = time.monotonic()

    def consume(self) -> tuple[bool, int]:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(_RATE_LIMIT, self.tokens + elapsed * (_RATE_LIMIT / _WINDOW_SECONDS))
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True, max(0, int(self.tokens))
        return False, 0


_buckets: dict[str, _TokenBucket] = defaultdict(_TokenBucket)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests exceeding the per-IP rate limit with 429."""

    async def dispatch(self, request: Request, call_next: any) -> Response:  # type: ignore[override]
        if settings.app_env == "development":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        try:
            allowed, remaining = _redis_consume(client_ip)
        except RuntimeError:
            bucket = _buckets[client_ip]
            allowed, remaining = bucket.consume()

        if not allowed:
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
