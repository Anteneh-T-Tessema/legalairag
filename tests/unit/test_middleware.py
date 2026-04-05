"""Tests for security headers, audit log, and rate limiting middleware."""

from __future__ import annotations

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
