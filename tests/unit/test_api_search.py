"""Tests for the search and ask API endpoints.

Search and ask depend on embedder, searcher, reranker, and agent — all mocked
to isolate HTTP-level validation, auth gating, and response shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.auth import Role, create_access_token
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _auth(role: Role = Role.ATTORNEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('testuser', role)}"}


# ── Fake result object returned by reranker ──────────────────────────────────


def _fake_result(chunk_id: str = "c1", source_id: str = "src-001"):
    obj = MagicMock()
    obj.chunk_id = chunk_id
    obj.source_id = source_id
    obj.section = "Section 1"
    obj.content = "This is a test chunk about Indiana property law."
    obj.citations = ["IC 32-17-5"]
    obj.score = 0.95
    return obj


def _fake_agent_result():
    obj = MagicMock()
    obj.answer = "Indiana law requires..."
    obj.source_ids = ["src-001"]
    obj.citations = ["IC 32-17-5"]
    obj.confidence = "high"
    obj.run_id = "run-123"
    obj.validation_passed = True
    return obj


# ── Search endpoint ──────────────────────────────────────────────────────────


class TestSearchEndpoint:
    @patch("api.routers.search._reranker")
    @patch("api.routers.search._searcher")
    @patch("api.routers.search._embedder")
    def test_search_success(self, mock_embedder, mock_searcher, mock_reranker):
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_searcher.search = AsyncMock(return_value=[_fake_result()])
        mock_reranker.rerank = AsyncMock(return_value=[_fake_result()])

        resp = client.post(
            "/api/v1/search",
            json={"query": "Indiana property law"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "Indiana property law"
        assert len(body["results"]) == 1
        assert body["results"][0]["source_id"] == "src-001"
        assert body["total"] == 1

    @patch("api.routers.search._reranker")
    @patch("api.routers.search._searcher")
    @patch("api.routers.search._embedder")
    def test_search_with_jurisdiction(self, mock_embedder, mock_searcher, mock_reranker):
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)
        mock_searcher.search = AsyncMock(return_value=[])
        mock_reranker.rerank = AsyncMock(return_value=[])

        resp = client.post(
            "/api/v1/search",
            json={"query": "criminal defense", "jurisdiction": "Marion", "top_k": 3},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["jurisdiction"] == "Marion"

    def test_search_no_auth(self):
        resp = client.post("/api/v1/search", json={"query": "test query"})
        assert resp.status_code == 401

    def test_search_short_query_rejected(self):
        resp = client.post("/api/v1/search", json={"query": "ab"}, headers=_auth())
        assert resp.status_code == 422

    def test_search_top_k_out_of_range(self):
        resp = client.post(
            "/api/v1/search", json={"query": "test query", "top_k": 50}, headers=_auth()
        )
        assert resp.status_code == 422


# ── Ask endpoint ──────────────────────────────────────────────────────────────


class TestAskEndpoint:
    @patch("api.routers.search._agent")
    def test_ask_success(self, mock_agent):
        result = _fake_agent_result()
        mock_agent.run = AsyncMock(return_value=result)

        resp = client.post(
            "/api/v1/search/ask",
            json={"query": "What is Indiana's statute of limitations?"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Indiana law requires..."
        assert body["run_id"] == "run-123"
        assert body["validation_passed"] is True

    def test_ask_no_auth(self):
        resp = client.post("/api/v1/search/ask", json={"query": "test question"})
        assert resp.status_code == 401

    def test_ask_short_query_rejected(self):
        resp = client.post("/api/v1/search/ask", json={"query": "ab"}, headers=_auth())
        assert resp.status_code == 422
