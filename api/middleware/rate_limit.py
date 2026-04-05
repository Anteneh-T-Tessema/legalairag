"""Rate limiting middleware using a simple in-memory token bucket.

For production deployments behind multiple ECS tasks, replace with
Redis-backed rate limiting (e.g. via ElastiCache) or AWS WAF.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings

# Requests per window per client IP
_RATE_LIMIT = 60  # requests
_WINDOW_SECONDS = 60  # per minute


class _TokenBucket:
    __slots__ = ("tokens", "last_refill")

    def __init__(self) -> None:
        self.tokens: float = _RATE_LIMIT
        self.last_refill: float = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(_RATE_LIMIT, self.tokens + elapsed * (_RATE_LIMIT / _WINDOW_SECONDS))
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


# Per-IP buckets (cleared naturally by GC when stale)
_buckets: dict[str, _TokenBucket] = defaultdict(_TokenBucket)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests exceeding the per-IP rate limit with 429."""

    async def dispatch(self, request: Request, call_next: any) -> Response:  # type: ignore[override]
        # Skip rate limiting in development
        if settings.app_env == "development":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = _buckets[client_ip]

        if not bucket.consume():
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(max(0, int(bucket.tokens)))
        return response
