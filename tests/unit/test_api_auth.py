"""Tests for auth endpoints: login, refresh, /me, and role-based access."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.auth import Role, create_access_token, create_refresh_token
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
        resp2 = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
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
