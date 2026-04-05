"""Tests for auth endpoints: login, refresh, /me, and role-based access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api.auth import (
    Role,
    _blacklist,
    _blacklist_lock,
    _prune_blacklist,
    create_access_token,
    create_refresh_token,
    is_token_revoked,
    revoke_token,
)
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _auth_header(username: str = "admin", role: Role = Role.ADMIN) -> dict[str, str]:
    token = create_access_token(username, role)
    return {"Authorization": f"Bearer {token}"}


# ── Login ────────────────────────────────────────────────────────────────────


class TestLogin:
    def test_login_success_admin(self):
        resp = client.post("/api/v1/auth/token", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    def test_login_success_attorney(self):
        resp = client.post(
            "/api/v1/auth/token", json={"username": "attorney", "password": "attorney123"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self):
        resp = client.post(
            "/api/v1/auth/token", json={"username": "admin", "password": "wrongpass"}
        )
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    def test_login_unknown_user(self):
        resp = client.post("/api/v1/auth/token", json={"username": "nobody", "password": "pass"})
        assert resp.status_code == 401

    def test_login_empty_username_rejected(self):
        resp = client.post("/api/v1/auth/token", json={"username": "", "password": "x"})
        assert resp.status_code == 422

    def test_login_missing_fields_rejected(self):
        resp = client.post("/api/v1/auth/token", json={})
        assert resp.status_code == 422


# ── Refresh ──────────────────────────────────────────────────────────────────


class TestRefresh:
    def test_refresh_returns_new_pair(self):
        # Login first
        login_resp = client.post(
            "/api/v1/auth/token", json={"username": "admin", "password": "admin123"}
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    def test_refresh_invalid_token(self):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
        assert resp.status_code == 401

    def test_refresh_rotates_token(self):
        """Using a refresh token should revoke it — second use must fail."""
        login_resp = client.post(
            "/api/v1/auth/token", json={"username": "admin", "password": "admin123"}
        )
        refresh_token = login_resp.json()["refresh_token"]

        # First use should succeed
        resp1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp1.status_code == 200

        # Second use of the same refresh token should fail (revoked)
        resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp2.status_code == 401
        assert "revoked" in resp2.json()["detail"].lower()


# ── Revocation ───────────────────────────────────────────────────────────────


class TestRevocation:
    def test_revoke_refresh_token(self):
        """POST /auth/revoke should invalidate a refresh token."""
        login_resp = client.post(
            "/api/v1/auth/token", json={"username": "admin", "password": "admin123"}
        )
        tokens = login_resp.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        resp = client.post(
            "/api/v1/auth/revoke",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert resp.status_code == 204

        # The revoked refresh token should no longer work
        resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert resp2.status_code == 401

    def test_revoke_requires_auth(self):
        token = create_refresh_token("admin")
        resp = client.post("/api/v1/auth/revoke", json={"refresh_token": token})
        assert resp.status_code == 401

    def test_revoke_cannot_revoke_other_users_token(self):
        """Users cannot revoke tokens belonging to a different user."""
        admin_login = client.post(
            "/api/v1/auth/token", json={"username": "admin", "password": "admin123"}
        )
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        attorney_login = client.post(
            "/api/v1/auth/token", json={"username": "attorney", "password": "attorney123"}
        )
        attorney_refresh = attorney_login.json()["refresh_token"]

        # Admin tries to revoke attorney's token
        resp = client.post(
            "/api/v1/auth/revoke",
            json={"refresh_token": attorney_refresh},
            headers=admin_headers,
        )
        assert resp.status_code == 403


# ── /me ──────────────────────────────────────────────────────────────────────


class TestMe:
    def test_me_returns_user_info(self):
        resp = client.get("/api/v1/auth/me", headers=_auth_header("admin", Role.ADMIN))
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"

    def test_me_attorney_role(self):
        resp = client.get("/api/v1/auth/me", headers=_auth_header("attorney", Role.ATTORNEY))
        assert resp.status_code == 200
        assert resp.json()["role"] == "attorney"

    def test_me_no_token_401(self):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_bad_token_401(self):
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401


# ── Health ───────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "env" in body


# ── Blacklist TTL eviction ───────────────────────────────────────────────────


class TestBlacklistEviction:
    """Verify in-memory blacklist entries expire and get pruned."""

    def _clear_blacklist(self):
        with _blacklist_lock:
            _blacklist.clear()

    def test_revoked_token_is_detected(self):
        self._clear_blacklist()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        revoke_token("test-jti-1", future)
        assert is_token_revoked("test-jti-1") is True

    def test_expired_entry_evicted_on_check(self):
        self._clear_blacklist()
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        with _blacklist_lock:
            _blacklist["old-jti"] = past.timestamp()
        # Should return False and remove the entry
        assert is_token_revoked("old-jti") is False
        with _blacklist_lock:
            assert "old-jti" not in _blacklist

    def test_prune_removes_expired(self):
        self._clear_blacklist()
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with _blacklist_lock:
            _blacklist["expired-1"] = past.timestamp()
            _blacklist["expired-2"] = past.timestamp()
            _blacklist["valid-1"] = future.timestamp()
            _prune_blacklist()
        with _blacklist_lock:
            assert "expired-1" not in _blacklist
            assert "expired-2" not in _blacklist
            assert "valid-1" in _blacklist

    def test_already_expired_token_not_added(self):
        self._clear_blacklist()
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        revoke_token("skip-jti", past)
        with _blacklist_lock:
            assert "skip-jti" not in _blacklist


# ── hash_password ────────────────────────────────────────────────────────────


class TestHashPassword:
    def test_hash_password_auto_generates_salt(self):
        """hash_password(pass, salt=None) generates a random salt (line 148)."""
        from api.auth import hash_password

        hashed, salt = hash_password("secret")
        assert isinstance(salt, str)
        assert len(salt) == 64  # 32 hex bytes
        # Same password + same salt should reproduce the same hash
        hashed2, _ = hash_password("secret", salt=salt)
        assert hashed == hashed2

    def test_hash_password_with_explicit_salt(self):
        from api.auth import hash_password

        hashed, returned_salt = hash_password("mypass", salt="fixed-salt")
        assert returned_salt == "fixed-salt"


# ── decode_token: ExpiredSignatureError branch ───────────────────────────────


class TestDecodeToken:
    def test_expired_token_raises_401(self):
        """jwt.ExpiredSignatureError → HTTPException 401 'Token expired' (line 218)."""
        import jwt as _jwt
        from fastapi import HTTPException

        from api.auth import _ALGORITHM, _SECRET, decode_token

        past = datetime.now(timezone.utc) - timedelta(hours=2)
        expired_token = _jwt.encode(
            {
                "sub": "admin",
                "role": "admin",
                "iat": (past - timedelta(minutes=60)).timestamp(),
                "exp": (past).timestamp(),
                "jti": "expired-jti-001",
            },
            _SECRET,
            algorithm=_ALGORITHM,
        )
        import pytest as _pytest

        with _pytest.raises(HTTPException) as exc_info:
            decode_token(expired_token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()


# ── get_current_user: missing role ───────────────────────────────────────────


class TestGetCurrentUser:
    def test_token_without_role_raises_401(self):
        """TokenPayload.role is None → HTTPException 401 (line 238)."""
        import jwt as _jwt

        from api.auth import _ALGORITHM, _SECRET

        now = datetime.now(timezone.utc)
        no_role_token = _jwt.encode(
            {
                "sub": "norole",
                # intentionally omit "role"
                "iat": now.timestamp(),
                "exp": (now + timedelta(hours=1)).timestamp(),
                "jti": "norole-jti-001",
            },
            _SECRET,
            algorithm=_ALGORITHM,
        )
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {no_role_token}"},
        )
        assert resp.status_code == 401


# ── Redis revocation paths ───────────────────────────────────────────────────


class TestRedisRevocation:
    def test_get_revocation_redis_with_valid_url(self):
        """_get_revocation_redis() exercises the Redis import path (lines 73-80)."""
        from unittest.mock import MagicMock, patch

        from api.auth import _get_revocation_redis

        mock_redis_client = MagicMock()
        mock_redis_client.ping.return_value = True
        mock_redis_lib = MagicMock()
        mock_redis_lib.Redis.from_url.return_value = mock_redis_client

        with (
            patch("api.auth.settings") as mock_settings,
            patch.dict("sys.modules", {"redis": mock_redis_lib}),
        ):
            mock_settings.redis_url = "redis://localhost:6379"
            r = _get_revocation_redis()

        assert r is mock_redis_client

    def test_get_revocation_redis_exception_returns_none(self):
        """Redis import raises → return None (lines 79-80)."""
        from unittest.mock import MagicMock, patch

        from api.auth import _get_revocation_redis

        mock_redis_lib = MagicMock()
        mock_redis_lib.Redis.from_url.side_effect = Exception("refused")

        with (
            patch("api.auth.settings") as mock_settings,
            patch.dict("sys.modules", {"redis": mock_redis_lib}),
        ):
            mock_settings.redis_url = "redis://localhost:6379"
            r = _get_revocation_redis()

        assert r is None

    def test_revoke_token_via_redis_success(self):
        """revoke_token() uses Redis setex when available (lines 90-92)."""
        from unittest.mock import MagicMock, patch

        from api.auth import revoke_token

        mock_redis = MagicMock()
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch("api.auth._get_revocation_redis", return_value=mock_redis):
            revoke_token("redis-jti", future)
        mock_redis.setex.assert_called_once()

    def test_revoke_token_redis_exception_falls_back_to_memory(self):
        """revoke_token() falls back to in-memory on Redis failure (lines 93-98)."""
        from unittest.mock import MagicMock, patch

        from api.auth import _blacklist, _blacklist_lock, revoke_token

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("connection error")
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        jti = "fallback-jti-001"

        with (
            patch("api.auth._get_revocation_redis", return_value=mock_redis),
            _blacklist_lock,
        ):
            _blacklist.pop(jti, None)

        with patch("api.auth._get_revocation_redis", return_value=mock_redis):
            revoke_token(jti, future)

        with _blacklist_lock:
            assert jti in _blacklist
            _blacklist.pop(jti, None)

    def test_is_token_revoked_via_redis_success(self):
        """is_token_revoked() queries Redis when available (lines 105-106)."""
        from unittest.mock import MagicMock, patch

        from api.auth import is_token_revoked

        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        with patch("api.auth._get_revocation_redis", return_value=mock_redis):
            assert is_token_revoked("some-jti") is True

    def test_is_token_revoked_redis_exception_falls_back(self):
        """is_token_revoked() falls back to memory on Redis error (lines 107-108)."""
        from unittest.mock import MagicMock, patch

        from api.auth import _blacklist, _blacklist_lock, is_token_revoked

        mock_redis = MagicMock()
        mock_redis.exists.side_effect = Exception("timeout")
        jti = "memory-fallback-jti"
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with _blacklist_lock:
            _blacklist[jti] = future.timestamp()
        with patch("api.auth._get_revocation_redis", return_value=mock_redis):
            result = is_token_revoked(jti)
        assert result is True
        with _blacklist_lock:
            _blacklist.pop(jti, None)


# ── Blacklist max size prune ─────────────────────────────────────────────────


class TestBlacklistPrune:
    def test_revoke_triggers_prune_at_max_size(self):
        """When blacklist hits _BLACKLIST_MAX_SIZE, _prune_blacklist() is called (line 97)."""
        from api.auth import _BLACKLIST_MAX_SIZE, _blacklist, _blacklist_lock, revoke_token

        with _blacklist_lock:
            _blacklist.clear()
            # Fill with already-expired entries so prune will remove them
            past_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
            for i in range(_BLACKLIST_MAX_SIZE):
                _blacklist[f"fill-{i}"] = past_ts

        future = datetime.now(timezone.utc) + timedelta(hours=1)
        revoke_token("trigger-prune-jti", future)

        with _blacklist_lock:
            # All expired fill entries should have been pruned
            assert "fill-0" not in _blacklist
            _blacklist.clear()
