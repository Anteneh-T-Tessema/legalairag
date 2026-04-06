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
    MyCaseClient,
    MyCaseSearchResult,
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


# ── IndianaCourtClient.__init__ (lines 58-60) ─────────────────────────────────


class TestIndianaCourtClientInit:
    def test_init_sets_api_key(self):
        """Direct __init__ covers lines 58-60."""
        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient"):
            client = IndianaCourtClient(api_key="my-test-key")
        assert client._api_key == "my-test-key"
        assert client._semaphore is not None
        assert client._client is not None


# ── IndianaCourtClient.search_cases optional params ──────────────────────────


def _make_court_client():
    """Create IndianaCourtClient with a mocked httpx client (bypasses __init__)."""
    client = IndianaCourtClient.__new__(IndianaCourtClient)
    client._semaphore = asyncio.Semaphore(5)
    client._client = AsyncMock()
    return client


SAMPLE_CASE_DATA = {
    "caseNumber": "49D01-2401-CT-000123",
    "court": "Marion Superior Court",
    "filingDate": "2024-01-15",
    "caseType": "Civil",
    "parties": [{"name": "Alice"}, {"name": "Bob"}],
    "summary": "Test",
    "county": "Marion",
}


def _mock_case_resp(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


class TestSearchCasesOptionalParams:
    def test_search_with_all_params(self):
        """Passes county, case_type, date_from, date_to — covers lines 88, 90, 92, 94."""
        c = _make_court_client()
        c._client.get = AsyncMock(return_value=_mock_case_resp({"items": [SAMPLE_CASE_DATA]}))
        cases = _run(
            c.search_cases(
                county="Marion",
                case_type="Civil",
                date_from=date(2024, 1, 1),
                date_to=date(2024, 12, 31),
            )
        )
        assert len(cases) == 1

    def test_search_no_query_covers_false_branch(self):
        """Call without query covers the 85->87 false branch."""
        c = _make_court_client()
        c._client.get = AsyncMock(return_value=_mock_case_resp({"items": []}))
        cases = _run(c.search_cases(county="Hamilton"))
        assert cases == []


# ── IndianaCourtClient.get_case (lines 101-105) ───────────────────────────────


class TestGetCase:
    def test_get_case_returns_case_with_documents(self):
        """get_case makes two _get calls and attaches documents (lines 101-105)."""
        c = _make_court_client()
        doc_data = {
            "documentId": "doc-1",
            "documentType": "Order",
            "filedDate": "2024-02-01",
            "downloadUrl": "https://example.com/doc.pdf",
        }
        # First call returns case data, second call returns documents
        c._client.get = AsyncMock(
            side_effect=[
                _mock_case_resp(SAMPLE_CASE_DATA),
                _mock_case_resp({"items": [doc_data]}),
            ]
        )
        case = _run(c.get_case("49D01-2401-CT-000123"))
        assert case.case_number == "49D01-2401-CT-000123"
        assert len(case.documents) == 1
        assert case.documents[0].doc_id == "doc-1"

    def test_get_case_with_no_documents(self):
        """get_case with empty documents still returns a valid CourtCase."""
        c = _make_court_client()
        c._client.get = AsyncMock(
            side_effect=[
                _mock_case_resp(SAMPLE_CASE_DATA),
                _mock_case_resp({"items": []}),
            ]
        )
        case = _run(c.get_case("49D01-2401-CT-000123"))
        assert case.documents == []


# ── IndianaCourtClient.download_document (lines 109-112) ─────────────────────


class TestDownloadDocument:
    def test_download_returns_bytes(self):
        """download_document acquires semaphore and returns response content (lines 109-112)."""
        c = _make_court_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.content = b"%PDF-1.4 binary-data"
        c._client.get = AsyncMock(return_value=mock_resp)

        doc = CaseDocument(
            doc_id="doc-1",
            case_number="49D01-2401-CT-000123",
            doc_type="Order",
            filed_date=date(2024, 2, 1),
            download_url="https://example.com/doc.pdf",
        )
        content = _run(c.download_document(doc))
        assert content == b"%PDF-1.4 binary-data"


# ── IndianaCourtClient.list_recent_filings (lines 120-123) ───────────────────


class TestListRecentFilings:
    def test_list_recent_filings_calls_search_cases(self):
        """list_recent_filings delegates to search_cases (lines 120-123)."""
        c = _make_court_client()
        c._client.get = AsyncMock(return_value=_mock_case_resp({"items": [SAMPLE_CASE_DATA]}))
        cases = _run(c.list_recent_filings("Marion", days_back=3))
        assert len(cases) == 1
        assert cases[0].jurisdiction == "Marion"


# ── IndianaCourtClient._get HTTPStatusError (lines 139-141) ──────────────────


class TestClientGetHTTPStatusError:
    def test_raises_http_status_error(self):
        """_get catches HTTPStatusError, logs, and re-raises (lines 139-141)."""
        c = _make_court_client()

        import httpx as _httpx

        real_req = _httpx.Request("GET", "http://test")
        real_resp = _httpx.Response(403, json={}, request=real_req)
        c._client.get = AsyncMock(
            side_effect=_httpx.HTTPStatusError("Forbidden", request=real_req, response=real_resp)
        )
        with pytest.raises(_httpx.HTTPStatusError):
            _run(c._get("/cases"))


# ── MyCaseClient ─────────────────────────────────────────────────────────────


def _make_mycase_client():
    """Create MyCaseClient bypassing __init__."""
    client = MyCaseClient.__new__(MyCaseClient)
    client._semaphore = asyncio.Semaphore(3)
    client._client = AsyncMock()
    return client


SAMPLE_MYCASE = {
    "caseNumber": "49D01-2401-CF-000789",
    "caseTypeCode": "CF",
    "court": "Marion Superior Court 7",
    "county": "Marion",
    "filingDate": "2024-03-01",
    "parties": [{"name": "State"}, {"name": "Defendant"}],
    "caseStatus": "Open",
    "judge": "Judge Smith",
    "nextHearing": "2024-09-15",
}


def _mock_mycase_resp(payload: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


class TestMyCaseClientInit:
    def test_init_sets_semaphore_and_client(self):
        """MyCaseClient.__init__ covers lines 330-331."""
        with patch("ingestion.sources.indiana_courts.httpx.AsyncClient"):
            client = MyCaseClient(max_concurrent=2, timeout=10.0)
        assert client._semaphore is not None
        assert client._client is not None

    def test_context_manager(self):
        """MyCaseClient __aenter__/__aexit__ cover lines 338, 341."""
        c = _make_mycase_client()
        result = _run(c.__aenter__())
        assert result is c
        _run(c.__aexit__(None, None, None))
        c._client.aclose.assert_awaited_once()


class TestMyCaseClientSearchByParty:
    def test_search_by_party_basic(self):
        """search_by_party without options (lines 353-364)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": [SAMPLE_MYCASE]}))
        results = _run(c.search_by_party("Smith"))
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, MyCaseSearchResult)
        assert result.case_number == "49D01-2401-CF-000789"
        assert result.next_hearing == date(2024, 9, 15)

    def test_search_by_party_with_county_and_type(self):
        """search_by_party with county and valid case_type_code (lines 358-361)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": [SAMPLE_MYCASE]}))
        results = _run(c.search_by_party("Smith", county="Marion", case_type_code="CF"))
        assert len(results) == 1

    def test_search_by_party_invalid_type_skips_param(self):
        """Invalid case_type_code is not added to params (covers False branch of 360)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": []}))
        results = _run(c.search_by_party("Jones", case_type_code="INVALID"))
        assert results == []

    def test_search_by_party_no_next_hearing(self):
        """_parse_result with no nextHearing field leaves next_hearing None."""
        c = _make_mycase_client()
        record_no_hearing = {**SAMPLE_MYCASE}
        del record_no_hearing["nextHearing"]
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": [record_no_hearing]}))
        results = _run(c.search_by_party("Smith"))
        assert results[0].next_hearing is None


class TestMyCaseClientSearchByCaseNumber:
    def test_search_by_case_number_success(self):
        """search_by_case_number returns result on success (lines 368-375)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp(SAMPLE_MYCASE))
        result = _run(c.search_by_case_number("49D01-2401-CF-000789"))
        assert result is not None
        assert result.case_number == "49D01-2401-CF-000789"

    def test_search_by_case_number_404(self):
        """search_by_case_number returns None on 404 (lines 373-374)."""
        import httpx as _httpx

        c = _make_mycase_client()
        req = _httpx.Request("GET", "http://test")
        resp_404 = _httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=_httpx.HTTPStatusError("Not found", request=req, response=resp_404)
        )
        assert _run(c.search_by_case_number("NONEXISTENT")) is None

    def test_search_by_case_number_reraises_non_404(self):
        """search_by_case_number re-raises non-404 errors (line 375)."""
        import httpx as _httpx

        c = _make_mycase_client()
        req = _httpx.Request("GET", "http://test")
        resp_500 = _httpx.Response(500, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=_httpx.HTTPStatusError("Error", request=req, response=resp_500)
        )
        with pytest.raises(_httpx.HTTPStatusError):
            _run(c.search_by_case_number("CASE-001"))


class TestMyCaseClientRecentFilings:
    def test_recent_filings_without_type(self):
        """recent_filings without case_type_code (lines 385-397)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": [SAMPLE_MYCASE]}))
        results = _run(c.recent_filings("Marion", days_back=7))
        assert len(results) == 1

    def test_recent_filings_with_valid_type(self):
        """recent_filings with valid case_type_code adds caseType param (line 393-394)."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": [SAMPLE_MYCASE]}))
        results = _run(c.recent_filings("Hamilton", case_type_code="CM", days_back=3))
        assert len(results) == 1


class TestMyCaseClientGet:
    def test_get_returns_json_on_success(self):
        """MyCaseClient._get covers lines 402-412."""
        c = _make_mycase_client()
        c._client.get = AsyncMock(return_value=_mock_mycase_resp({"results": []}))
        result = _run(c._get("/search/party"))
        assert result == {"results": []}

    def test_get_raises_after_three_429s(self):
        """MyCaseClient._get raises RuntimeError after exhausting retries (lines 402-416)."""
        c = _make_mycase_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        c._client.get = AsyncMock(return_value=mock_resp)

        with patch("ingestion.sources.indiana_courts.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Exhausted retries for mycase"):
                _run(c._get("/search/party"))

    def test_get_raises_http_status_error(self):
        """MyCaseClient._get logs and re-raises HTTPStatusError (lines 413-415)."""
        import httpx as _httpx

        c = _make_mycase_client()
        req = _httpx.Request("GET", "http://test")
        resp_503 = _httpx.Response(503, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=_httpx.HTTPStatusError("Unavailable", request=req, response=resp_503)
        )
        with pytest.raises(_httpx.HTTPStatusError):
            _run(c._get("/search/party"))
