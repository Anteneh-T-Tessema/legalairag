"""Tests for the fraud analysis API endpoint.

The fraud router depends on FraudDetectionAgent.  We mock the agent to
isolate HTTP-level behaviour (validation, auth, response shape).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from agents.fraud_detection_agent import FraudAnalysisResult, FraudIndicator
from api.auth import Role, create_access_token
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _auth(role: Role = Role.ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('testuser', role)}"}


def _mock_fraud_result() -> FraudAnalysisResult:
    return FraudAnalysisResult(
        run_id="test-run-001",
        query_context="John Doe property fraud",
        risk_level="high",
        requires_human_review=True,
        total_filings_analyzed=42,
        flagged_source_ids=["IND-2024-001", "IND-2024-002"],
        summary="Suspicious burst filing detected.",
        indicators=[
            FraudIndicator(
                indicator_type="burst_filing",
                severity="high",
                description="12 filings in 3 days",
                evidence=["IND-2024-001", "IND-2024-002"],
                confidence=0.92,
            ),
        ],
    )


class TestFraudEndpoint:
    @patch("api.routers.fraud._agent")
    def test_fraud_analyze_success(self, mock_agent):
        mock_agent.run = AsyncMock(return_value=_mock_fraud_result())
        resp = client.post(
            "/api/v1/fraud/analyze",
            json={"query": "John Doe property fraud"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_level"] == "high"
        assert body["requires_human_review"] is True
        assert len(body["indicators"]) == 1
        assert body["indicators"][0]["indicator_type"] == "burst_filing"
        assert body["run_id"] == "test-run-001"
        assert body["flagged_source_ids"] == ["IND-2024-001", "IND-2024-002"]

    @patch("api.routers.fraud._agent")
    def test_fraud_analyze_returns_summary(self, mock_agent):
        mock_agent.run = AsyncMock(return_value=_mock_fraud_result())
        resp = client.post(
            "/api/v1/fraud/analyze",
            json={"query": "burst filings"},
            headers=_auth(),
        )
        assert resp.json()["summary"] == "Suspicious burst filing detected."

    def test_fraud_analyze_no_auth_returns_401(self):
        resp = client.post("/api/v1/fraud/analyze", json={"query": "test query"})
        assert resp.status_code == 401

    def test_fraud_analyze_short_query_rejected(self):
        resp = client.post(
            "/api/v1/fraud/analyze",
            json={"query": "ab"},  # min_length=3
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_fraud_analyze_empty_body_rejected(self):
        resp = client.post("/api/v1/fraud/analyze", json={}, headers=_auth())
        assert resp.status_code == 422

    @patch("api.routers.fraud._agent")
    def test_fraud_agent_error_returns_500(self, mock_agent):
        mock_agent.run = AsyncMock(side_effect=RuntimeError("model down"))
        resp = client.post(
            "/api/v1/fraud/analyze",
            json={"query": "test query"},
            headers=_auth(),
        )
        assert resp.status_code == 500
        assert "Fraud detection failed" in resp.json()["detail"]
