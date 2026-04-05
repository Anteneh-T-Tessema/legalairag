"""Unit tests for api.main – FastAPI app wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Health endpoint ───────────────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_returns_200(self):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_returns_status_ok(self):
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_health_includes_env(self):
        body = client.get("/health").json()
        assert "env" in body


# ── Metrics endpoint ──────────────────────────────────────────────────────────


class TestMetricsEndpoint:
    def test_prometheus_metrics_returns_200(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")

    def test_json_metrics_returns_200(self):
        r = client.get("/metrics/json")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)


# ── Router inclusion ──────────────────────────────────────────────────────────


class TestRouterInclusion:
    """Verify all expected routers are mounted under /api/v1."""

    def test_auth_routes_mounted(self):
        routes = {r.path for r in app.routes}
        assert "/api/v1/auth/token" in routes

    def test_search_routes_mounted(self):
        routes = {r.path for r in app.routes}
        assert "/api/v1/search" in routes

    def test_documents_routes_mounted(self):
        routes = {r.path for r in app.routes}
        assert "/api/v1/documents/ingest" in routes

    def test_fraud_routes_mounted(self):
        routes = {r.path for r in app.routes}
        assert "/api/v1/fraud/analyze" in routes


# ── Middleware ordering ───────────────────────────────────────────────────────


class TestMiddleware:
    def test_security_headers_present(self):
        r = client.get("/health")
        assert "x-content-type-options" in r.headers

    def test_cors_preflight(self):
        r = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should respond (may vary based on allow_origins)
        assert r.status_code in (200, 400)

    def test_unknown_route_returns_404(self):
        r = client.get("/api/v1/nonexistent")
        assert r.status_code in (404, 405)


# ── OpenAPI docs ──────────────────────────────────────────────────────────────


class TestDocs:
    def test_openapi_schema_available(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema["info"]["title"] == "IndyLeg — Indiana Legal RAG Platform"
        assert "0.2.0" in schema["info"]["version"]
