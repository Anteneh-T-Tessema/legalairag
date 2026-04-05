"""Tests for the document ingest API endpoint.

The documents router requires ADMIN or ATTORNEY role and publishes to SQS.
We mock the SQS producer to isolate HTTP-level behaviour.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.auth import Role, create_access_token
from api.main import app

client = TestClient(app, raise_server_exceptions=False)


def _auth(role: Role = Role.ADMIN) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('testuser', role)}"}


class TestDocumentsEndpoint:
    @patch("api.routers.documents._producer")
    def test_ingest_success(self, mock_producer):
        mock_producer.publish = AsyncMock(return_value="msg-001")
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "indiana_courts",
                "source_id": "IND-2024-001",
                "download_url": "https://example.com/doc.pdf",
                "metadata": {"county": "Marion"},
            },
            headers=_auth(Role.ADMIN),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["message_id"] == "msg-001"
        assert body["source_id"] == "IND-2024-001"
        assert body["queued"] is True

    @patch("api.routers.documents._producer")
    def test_ingest_attorney_allowed(self, mock_producer):
        mock_producer.publish = AsyncMock(return_value="msg-002")
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "s3_upload",
                "source_id": "DOC-001",
                "download_url": "https://example.com/doc.pdf",
            },
            headers=_auth(Role.ATTORNEY),
        )
        assert resp.status_code == 202

    def test_ingest_clerk_forbidden(self):
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "indiana_courts",
                "source_id": "IND-2024-002",
                "download_url": "https://example.com/doc.pdf",
            },
            headers=_auth(Role.CLERK),
        )
        assert resp.status_code == 403

    def test_ingest_viewer_forbidden(self):
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "indiana_courts",
                "source_id": "IND-2024-003",
                "download_url": "https://example.com/doc.pdf",
            },
            headers=_auth(Role.VIEWER),
        )
        assert resp.status_code == 403

    def test_ingest_no_auth(self):
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "indiana_courts",
                "source_id": "IND-2024-004",
                "download_url": "https://example.com/doc.pdf",
            },
        )
        assert resp.status_code == 401

    def test_ingest_missing_fields_rejected(self):
        resp = client.post(
            "/api/v1/documents/ingest",
            json={"source_type": "indiana_courts"},
            headers=_auth(Role.ADMIN),
        )
        assert resp.status_code == 422

    @patch("api.routers.documents._producer")
    def test_ingest_sqs_failure_returns_503(self, mock_producer):
        mock_producer.publish = AsyncMock(side_effect=RuntimeError("SQS down"))
        resp = client.post(
            "/api/v1/documents/ingest",
            json={
                "source_type": "indiana_courts",
                "source_id": "IND-2024-005",
                "download_url": "https://example.com/doc.pdf",
            },
            headers=_auth(Role.ADMIN),
        )
        assert resp.status_code == 503
        assert "Failed to queue" in resp.json()["detail"]
