"""Unit tests for ingestion.sources.indiana_courts — IndianaCourtClient + helpers."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.sources.indiana_courts import (
    CaseDocument,
    CourtCase,
    IndianaCourtClient,
    _sanitize_case_number,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _sanitize_case_number ─────────────────────────────────────────────────────


class TestSanitizeCaseNumber:
    def test_allows_alphanumeric_and_hyphens(self):
        assert _sanitize_case_number("49D01-2401-CT-000123") == "49D01-2401-CT-000123"

    def test_strips_path_traversal(self):
        assert _sanitize_case_number("../../../etc/passwd") == "etcpasswd"

    def test_strips_special_chars(self):
        assert _sanitize_case_number("CASE#12; DROP TABLE") == "CASE12DROPTABLE"

    def test_empty_input(self):
        assert _sanitize_case_number("") == ""


# ── IndianaCourtClient._parse_case ────────────────────────────────────────────


class TestParseCase:
    def test_parses_valid_case(self):
        data = {
            "caseNumber": "49D01-2401-CT-000123",
            "court": "Marion Superior Court",
            "filingDate": "2024-01-15",
            "caseType": "Civil",
            "parties": [{"name": "Alice"}, {"name": "Bob"}],
            "summary": "Property dispute",
            "county": "Marion County",
        }
        case = IndianaCourtClient._parse_case(data)
        assert isinstance(case, CourtCase)
        assert case.case_number == "49D01-2401-CT-000123"
        assert case.court == "Marion Superior Court"
        assert case.filing_date == date(2024, 1, 15)
        assert case.parties == ["Alice", "Bob"]
        assert case.jurisdiction == "Marion County"

    def test_missing_optional_fields(self):
        data = {
            "caseNumber": "C-1",
            "filingDate": "2024-06-01",
        }
        case = IndianaCourtClient._parse_case(data)
        assert case.court == ""
        assert case.case_type == "Unknown"
        assert case.jurisdiction == "Indiana"


# ── IndianaCourtClient._parse_document ────────────────────────────────────────


class TestParseDocument:
    def test_parses_valid_document(self):
        data = {
            "documentId": "doc-42",
            "documentType": "Order",
            "filedDate": "2024-02-10",
            "downloadUrl": "https://example.com/doc.pdf",
            "description": "Preliminary ruling",
        }
        doc = IndianaCourtClient._parse_document(data, "CASE-1")
        assert isinstance(doc, CaseDocument)
        assert doc.doc_id == "doc-42"
        assert doc.case_number == "CASE-1"
        assert doc.doc_type == "Order"
        assert doc.filed_date == date(2024, 2, 10)

    def test_missing_optional_fields(self):
        data = {
            "documentId": "d1",
            "filedDate": "2024-01-01",
            "downloadUrl": "https://example.com/d1",
        }
        doc = IndianaCourtClient._parse_document(data, "C-1")
        assert doc.doc_type == "Unknown"
        assert doc.description == ""


# ── IndianaCourtClient._get (retry logic) ────────────────────────────────────


class TestClientGet:
    def test_returns_json_on_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"items": []}

        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value = mock_http
            mock_http.get = AsyncMock(return_value=mock_resp)

            client = IndianaCourtClient.__new__(IndianaCourtClient)
            client._semaphore = asyncio.Semaphore(5)
            client._client = mock_http

            result = _run(client._get("/cases"))
            assert result == {"items": []}

    def test_raises_after_retries_exhausted_on_429(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            MockClient.return_value = mock_http
            mock_http.get = AsyncMock(return_value=mock_resp)

            client = IndianaCourtClient.__new__(IndianaCourtClient)
            client._semaphore = asyncio.Semaphore(5)
            client._client = mock_http

            with patch("ingestion.sources.indiana_courts.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="Exhausted retries"):
                    _run(client._get("/cases"))


# ── IndianaCourtClient.search_cases ───────────────────────────────────────────


class TestSearchCases:
    def test_search_returns_parsed_cases(self):
        case_data = {
            "items": [
                {
                    "caseNumber": "C-1",
                    "filingDate": "2024-01-01",
                    "court": "Test Court",
                    "caseType": "Civil",
                    "parties": [],
                    "summary": "Test",
                    "county": "Test County",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = case_data

        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient"):
            client = IndianaCourtClient.__new__(IndianaCourtClient)
            client._semaphore = asyncio.Semaphore(5)
            client._client = AsyncMock()
            client._client.get = AsyncMock(return_value=mock_resp)

            cases = _run(client.search_cases(query="eviction"))
            assert len(cases) == 1
            assert cases[0].case_number == "C-1"


# ── Context manager ──────────────────────────────────────────────────────────


class TestContextManager:
    def test_aenter_returns_self(self):
        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient"):
            client = IndianaCourtClient.__new__(IndianaCourtClient)
            client._client = AsyncMock()
            result = _run(client.__aenter__())
            assert result is client

    def test_aexit_closes_client(self):
        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient"):
            client = IndianaCourtClient.__new__(IndianaCourtClient)
            client._client = AsyncMock()
            _run(client.__aexit__(None, None, None))
            client._client.aclose.assert_called_once()
