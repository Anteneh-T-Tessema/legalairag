"""Tests for security headers, audit log, and rate limiting middleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestSecurityHeaders:
    """Verify OWASP-recommended security headers on every response."""

    def test_x_content_type_options(self):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self):
        resp = client.get("/health")
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_referrer_policy(self):
        resp = client.get("/health")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self):
        resp = client.get("/health")
        assert resp.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"

    def test_no_hsts_on_http(self):
        """HSTS should only be set over HTTPS, not plain HTTP."""
        resp = client.get("/health")
        assert "Strict-Transport-Security" not in resp.headers


class TestAuditLog:
    """Verify audit log middleware adds X-Request-Id."""

    def test_request_id_header_present(self):
        resp = client.get("/health")
        request_id = resp.headers.get("X-Request-Id")
        assert request_id is not None
        # UUID format: 8-4-4-4-12
        parts = request_id.split("-")
        assert len(parts) == 5

    def test_request_id_unique_per_call(self):
        resp1 = client.get("/health")
        resp2 = client.get("/health")
        assert resp1.headers["X-Request-Id"] != resp2.headers["X-Request-Id"]


class TestRateLimit:
    """Rate limiter is skipped in development mode. Test the header plumbing."""

    def test_rate_limit_headers_absent_in_dev(self):
        """In development mode, rate limiter is bypassed so no X-RateLimit headers."""
        resp = client.get("/health")
        # The rate limit middleware skips processing in development env,
        # so these headers should not be present.
        # (settings.app_env defaults to "development")
        assert "X-RateLimit-Limit" not in resp.headers


class TestRateLimiterRedisReset:
    """Verify that a failed Redis operation resets the cached client."""

    def test_redis_reset_on_error(self):
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        # Simulate a previously-cached (now-broken) Redis client
        fake_redis = MagicMock()
        fake_redis.incr.side_effect = ConnectionError("gone")
        rl_mod._redis = fake_redis

        # _redis_consume should raise RuntimeError *and* reset _redis to None
        import pytest

        with pytest.raises(RuntimeError, match="redis error"):
            rl_mod._redis_consume("127.0.0.1")

        assert rl_mod._redis is None

        # Cleanup
        rl_mod._redis = None


class TestTokenBucket:
    """Verify _TokenBucket in-memory refill and consume logic."""

    def test_fresh_bucket_allows_consume(self) -> None:
        from api.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket()
        allowed, remaining = bucket.consume()
        assert allowed is True
        assert remaining >= 0

    def test_bucket_returns_false_when_empty(self) -> None:
        from api.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket()
        bucket.tokens = 0.0
        allowed, remaining = bucket.consume()
        assert allowed is False
        assert remaining == 0

    def test_tokens_decrease_on_successive_consumes(self) -> None:
        from api.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket()
        _, r1 = bucket.consume()
        _, r2 = bucket.consume()
        assert r2 <= r1

    def test_bucket_refills_after_elapsed_time(self) -> None:
        import time
        from unittest.mock import patch

        from api.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket()
        bucket.tokens = 0.0
        frozen_start = time.monotonic()
        bucket.last_refill = frozen_start

        # Mock 30 s elapsed — should refill half the rate limit worth of tokens
        with patch("api.middleware.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = frozen_start + 30.0
            allowed, _ = bucket.consume()

        assert allowed is True  # refill should have granted at least one token

    def test_consume_returns_int_remaining(self) -> None:
        from api.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket()
        allowed, remaining = bucket.consume()
        assert isinstance(remaining, int)


class TestRedisConsume:
    """Direct unit tests for _redis_consume without a live Redis server."""

    def test_allowed_under_limit(self) -> None:
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        fake_redis = MagicMock()
        fake_redis.incr.return_value = 5
        fake_redis.expire.return_value = True
        fake_redis.ttl.return_value = 55
        rl_mod._redis = fake_redis

        try:
            allowed, remaining = rl_mod._redis_consume("10.0.0.1")
            assert allowed is True
            assert remaining == rl_mod._RATE_LIMIT - 5
        finally:
            rl_mod._redis = None

    def test_rate_exceeded_returns_false(self) -> None:
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        fake_redis = MagicMock()
        fake_redis.incr.return_value = rl_mod._RATE_LIMIT + 10
        fake_redis.expire.return_value = True
        fake_redis.ttl.return_value = 30
        rl_mod._redis = fake_redis

        try:
            allowed, remaining = rl_mod._redis_consume("10.0.0.2")
            assert allowed is False
            assert remaining == 0
        finally:
            rl_mod._redis = None

    def test_expire_called_on_first_request(self) -> None:
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        fake_redis = MagicMock()
        fake_redis.incr.return_value = 1  # first request → current == 1
        fake_redis.expire.return_value = True
        fake_redis.ttl.return_value = 60
        rl_mod._redis = fake_redis

        try:
            rl_mod._redis_consume("10.0.0.3")
            fake_redis.expire.assert_called()
        finally:
            rl_mod._redis = None

    def test_expire_called_when_ttl_missing(self) -> None:
        """ttl == -1 means no expiry was set; middleware must fix it."""
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        fake_redis = MagicMock()
        fake_redis.incr.return_value = 2
        fake_redis.expire.return_value = True
        fake_redis.ttl.return_value = -1  # missing TTL
        rl_mod._redis = fake_redis

        try:
            rl_mod._redis_consume("10.0.0.4")
            # expire must be called twice: first for incr==1 path is skipped,
            # but the ttl==-1 guard fires
            fake_redis.expire.assert_called()
        finally:
            rl_mod._redis = None

    def test_raises_runtime_error_and_resets_on_exception(self) -> None:
        from unittest.mock import MagicMock

        import api.middleware.rate_limit as rl_mod

        fake_redis = MagicMock()
        fake_redis.incr.side_effect = OSError("connection lost")
        rl_mod._redis = fake_redis

        with pytest.raises(RuntimeError, match="redis error"):
            rl_mod._redis_consume("10.0.0.5")

        assert rl_mod._redis is None

    def test_raises_no_redis_when_redis_url_not_configured(self) -> None:
        """When no redis_url is set, _get_redis returns None → RuntimeError('no redis')."""
        import api.middleware.rate_limit as rl_mod

        rl_mod._redis = None  # ensure no cached client
        # In test env, settings.redis_url is "" so _get_redis() returns None
        with pytest.raises(RuntimeError, match="no redis"):
            rl_mod._redis_consume("10.0.0.6")


class TestRateLimitProductionDispatch:
    """Test RateLimitMiddleware.dispatch() in production mode (non-development)."""

    def test_rate_limit_headers_present_when_allowed(self) -> None:
        """In production mode with available tokens, X-RateLimit-* headers are added."""
        from unittest.mock import patch

        import api.middleware.rate_limit as rl_mod

        original_env = rl_mod.settings.app_env
        rl_mod.settings.app_env = "production"
        try:
            # Redis unavailable → falls back to in-memory bucket (full tokens)
            rl_mod._buckets.clear()
            with patch(
                "api.middleware.rate_limit._redis_consume",
                side_effect=RuntimeError("no redis"),
            ):
                resp = client.get("/health")
            assert "X-RateLimit-Limit" in resp.headers
            assert "X-RateLimit-Remaining" in resp.headers
        finally:
            rl_mod.settings.app_env = original_env

    def test_returns_429_when_bucket_exhausted(self) -> None:
        """In production mode, an exhausted token bucket returns 429 with Retry-After."""
        from unittest.mock import patch

        import api.middleware.rate_limit as rl_mod

        original_env = rl_mod.settings.app_env
        rl_mod.settings.app_env = "production"
        try:
            exhausted = rl_mod._TokenBucket()
            exhausted.tokens = 0.0

            with (
                patch(
                    "api.middleware.rate_limit._redis_consume",
                    side_effect=RuntimeError("no redis"),
                ),
                patch.dict(rl_mod._buckets, {"testclient": exhausted}),
            ):
                resp = client.get("/health")

            assert resp.status_code == 429
            assert "Retry-After" in resp.headers
        finally:
            rl_mod.settings.app_env = original_env

    def test_redis_allowed_path_sets_headers(self) -> None:
        """In production mode, a successful Redis consume adds rate-limit headers."""
        from unittest.mock import patch

        import api.middleware.rate_limit as rl_mod

        original_env = rl_mod.settings.app_env
        rl_mod.settings.app_env = "production"
        try:
            with patch(
                "api.middleware.rate_limit._redis_consume",
                return_value=(True, 55),
            ):
                resp = client.get("/health")

            assert resp.headers.get("X-RateLimit-Remaining") == "55"
        finally:
            rl_mod.settings.app_env = original_env


# ── HTTPS / HSTS header ───────────────────────────────────────────────────────


class TestHTTPSHeaders:
    def test_hsts_header_present_on_https_scheme(self) -> None:
        """SecurityHeadersMiddleware sets HSTS header when scheme is https."""
        https_client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
        resp = https_client.get("/health")
        hsts = "max-age=31536000; includeSubDomains"
        assert resp.headers.get("Strict-Transport-Security") == hsts


# ── Metrics ring-buffer and Prometheus formatting ─────────────────────────────


class TestMetricsInternals:
    def test_ring_buffer_eviction_on_overflow(self) -> None:
        """When buffer is at _MAX_LATENCY_SAMPLES, _record pops oldest entry."""
        import api.middleware.metrics as metrics_mod

        # _record builds key as f"{method} {path}" — must use same format here
        key = "GET _test_overflow_eviction_"
        buf = metrics_mod._latencies[key]
        buf.clear()
        # Pre-fill to the maximum size
        for i in range(metrics_mod._MAX_LATENCY_SAMPLES):
            buf.append(float(i))
        assert len(buf) == metrics_mod._MAX_LATENCY_SAMPLES

        # One more record should evict the first entry and append the new one
        metrics_mod._record("GET", "_test_overflow_eviction_", 200, 9999.0)
        assert len(buf) == metrics_mod._MAX_LATENCY_SAMPLES
        assert buf[-1] == 9999.0

        # Cleanup
        del metrics_mod._latencies[key]
        del metrics_mod._request_count[key]

    def test_format_prometheus_skips_key_with_empty_latencies(self) -> None:
        """format_prometheus skips route entries that have an empty latency list."""
        import api.middleware.metrics as metrics_mod

        key = "GET /phantom_route_empty"
        # Inject an entry with no latency samples — the `if not lats: continue` branch
        metrics_mod._latencies[key] = []
        metrics_mod._request_count[key] = 3

        result = metrics_mod.format_prometheus()
        # The requests counter should appear but the duration section should skip this key
        assert "http_requests_total" in result
        assert 'path="/phantom_route_empty",quantile="0.5"' not in result

        # Cleanup
        del metrics_mod._latencies[key]
        del metrics_mod._request_count[key]


# ── Redis lazy-init (_get_redis) ─────────────────────────────────────────────


class TestGetRedisInit:
    """Covers the _get_redis() try/except block (lines 41-55 in rate_limit.py)."""

    def setup_method(self) -> None:
        import api.middleware.rate_limit as rl_mod

        self._rl_mod = rl_mod
        # Ensure no cached client so _get_redis runs the full init path
        self._orig_redis = rl_mod._redis
        rl_mod._redis = None

    def teardown_method(self) -> None:
        self._rl_mod._redis = self._orig_redis

    def test_get_redis_returns_client_on_successful_ping(self) -> None:
        import sys
        import types
        from unittest.mock import MagicMock

        rl_mod = self._rl_mod

        fake_redis_lib = types.ModuleType("redis")
        mock_conn = MagicMock()
        mock_conn.ping.return_value = True
        fake_redis_lib.Redis = MagicMock()
        fake_redis_lib.Redis.from_url = MagicMock(return_value=mock_conn)

        orig_url = rl_mod.settings.redis_url
        rl_mod.settings.redis_url = "redis://localhost:6379/0"
        orig_redis_mod = sys.modules.get("redis")
        sys.modules["redis"] = fake_redis_lib
        try:
            result = rl_mod._get_redis()
            assert result is mock_conn
        finally:
            rl_mod.settings.redis_url = orig_url
            if orig_redis_mod is None:
                sys.modules.pop("redis", None)
            else:
                sys.modules["redis"] = orig_redis_mod
            rl_mod._redis = None

    def test_get_redis_returns_none_when_ping_raises(self) -> None:
        import sys
        import types
        from unittest.mock import MagicMock

        rl_mod = self._rl_mod

        fake_redis_lib = types.ModuleType("redis")
        mock_conn = MagicMock()
        mock_conn.ping.side_effect = ConnectionRefusedError("refused")
        fake_redis_lib.Redis = MagicMock()
        fake_redis_lib.Redis.from_url = MagicMock(return_value=mock_conn)

        orig_url = rl_mod.settings.redis_url
        rl_mod.settings.redis_url = "redis://localhost:6379/0"
        orig_redis_mod = sys.modules.get("redis")
        sys.modules["redis"] = fake_redis_lib
        try:
            result = rl_mod._get_redis()
            assert result is None
            assert rl_mod._redis is None
        finally:
            rl_mod.settings.redis_url = orig_url
            if orig_redis_mod is None:
                sys.modules.pop("redis", None)
            else:
                sys.modules["redis"] = orig_redis_mod
            rl_mod._redis = None
