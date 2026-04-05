"""Unit tests for MyCaseClient and related constants in indiana_courts module."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingestion.sources.indiana_courts import (
    CASE_TYPE_CODES,
    INDIANA_COUNTIES,
    MyCaseClient,
    MyCaseSearchResult,
    _sanitize_case_number,
)

# ── Constants ─────────────────────────────────────────────────────────────────


class TestIndianaCounties:
    def test_has_92_counties(self) -> None:
        assert len(INDIANA_COUNTIES) == 92

    def test_contains_known_counties(self) -> None:
        for county in ["Marion", "Allen", "Lake", "Hamilton", "St. Joseph", "Vanderburgh"]:
            assert county in INDIANA_COUNTIES

    def test_no_duplicates(self) -> None:
        assert len(INDIANA_COUNTIES) == len(set(INDIANA_COUNTIES))

    def test_sorted_order(self) -> None:
        # Counties are roughly alphabetical; verify first and last.
        assert INDIANA_COUNTIES[0] == "Adams"
        assert INDIANA_COUNTIES[-1] == "Whitley"


class TestCaseTypeCodes:
    def test_has_22_codes(self) -> None:
        assert len(CASE_TYPE_CODES) == 22

    def test_criminal_codes(self) -> None:
        assert CASE_TYPE_CODES["CF"] == "Criminal Felony"
        assert CASE_TYPE_CODES["CM"] == "Criminal Misdemeanor"

    def test_civil_codes(self) -> None:
        assert CASE_TYPE_CODES["CT"] == "Civil Tort"
        assert CASE_TYPE_CODES["CC"] == "Civil Collection"
        assert CASE_TYPE_CODES["PL"] == "Civil Plenary"
        assert CASE_TYPE_CODES["SC"] == "Small Claims"

    def test_family_codes(self) -> None:
        assert CASE_TYPE_CODES["DR"] == "Domestic Relations"
        assert CASE_TYPE_CODES["PO"] == "Protective Order"
        assert CASE_TYPE_CODES["AD"] == "Adoption"

    def test_juvenile_codes(self) -> None:
        assert CASE_TYPE_CODES["JP"] == "Juvenile — CHINS/TPR"
        assert CASE_TYPE_CODES["JD"] == "Juvenile — Delinquency"
        assert CASE_TYPE_CODES["JS"] == "Juvenile — Status"

    def test_expungement(self) -> None:
        assert CASE_TYPE_CODES["XP"] == "Expungement"


# ── Sanitisation ──────────────────────────────────────────────────────────────


class TestSanitizeCaseNumber:
    def test_alphanumeric_unchanged(self) -> None:
        assert _sanitize_case_number("49D01-2401-CF-000123") == "49D01-2401-CF-000123"

    def test_strips_slashes(self) -> None:
        assert _sanitize_case_number("../../etc/passwd") == "etcpasswd"

    def test_strips_special_chars(self) -> None:
        assert _sanitize_case_number("49D01; DROP TABLE") == "49D01DROPTABLE"

    def test_empty_string(self) -> None:
        assert _sanitize_case_number("") == ""


# ── MyCaseClient ──────────────────────────────────────────────────────────────

SAMPLE_RESULT = {
    "caseNumber": "49D01-2401-CF-000123",
    "caseTypeCode": "CF",
    "caseType": "Criminal Felony",
    "court": "Marion Superior Court 1",
    "county": "Marion",
    "filingDate": "2024-01-15",
    "parties": [{"name": "State of Indiana"}, {"name": "John Doe"}],
    "caseStatus": "Open",
    "judge": "Hon. Jane Smith",
    "nextHearing": "2024-03-10",
}

SAMPLE_RESULT_NO_HEARING = {
    "caseNumber": "49D02-2402-SC-000456",
    "caseTypeCode": "SC",
    "court": "Marion Superior Court 2",
    "county": "Marion",
    "filingDate": "2024-02-20",
    "parties": [{"name": "Alice"}, {"name": "Bob"}],
    "caseStatus": "Closed",
    "judge": "Hon. James Brown",
}


class TestMyCaseClientParseResult:
    def test_parse_full_result(self) -> None:
        result = MyCaseClient._parse_result(SAMPLE_RESULT)
        assert isinstance(result, MyCaseSearchResult)
        assert result.case_number == "49D01-2401-CF-000123"
        assert result.case_type == "Criminal Felony"
        assert result.case_type_code == "CF"
        assert result.court == "Marion Superior Court 1"
        assert result.county == "Marion"
        assert result.filing_date == date(2024, 1, 15)
        assert result.parties == ["State of Indiana", "John Doe"]
        assert result.status == "Open"
        assert result.judge == "Hon. Jane Smith"
        assert result.next_hearing == date(2024, 3, 10)

    def test_parse_no_hearing(self) -> None:
        result = MyCaseClient._parse_result(SAMPLE_RESULT_NO_HEARING)
        assert result.next_hearing is None
        assert result.case_type == "Small Claims"
        assert result.status == "Closed"

    def test_parse_unknown_case_type_code(self) -> None:
        data = {**SAMPLE_RESULT, "caseTypeCode": "ZZ", "caseType": "Special"}
        result = MyCaseClient._parse_result(data)
        assert result.case_type == "Special"
        assert result.case_type_code == "ZZ"

    def test_parse_missing_fields_uses_defaults(self) -> None:
        result = MyCaseClient._parse_result({})
        assert result.case_number == ""
        assert result.case_type == "Unknown"
        assert result.status == "Unknown"
        assert result.parties == []
        assert result.filing_date == date(1970, 1, 1)


# ── Async client methods ─────────────────────────────────────────────────────


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "http://test")
    resp = httpx.Response(status_code=status_code, json=json_data, request=request)
    return resp


@pytest.fixture()
def client() -> MyCaseClient:
    """Create a MyCaseClient with mocked httpx internals."""
    with patch.object(MyCaseClient, "__init__", lambda self, **kw: None):
        c = MyCaseClient.__new__(MyCaseClient)
        c._semaphore = asyncio.Semaphore(3)
        c._client = AsyncMock(spec=httpx.AsyncClient)
        return c


class TestSearchByParty:
    def test_builds_correct_params(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response({"results": [SAMPLE_RESULT]}))
        results = asyncio.get_event_loop().run_until_complete(
            client.search_by_party("John Doe", county="Marion", case_type_code="CF")
        )
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["partyName"] == "John Doe"
        assert params["county"] == "Marion"
        assert params["caseType"] == "CF"
        assert len(results) == 1
        assert results[0].case_number == "49D01-2401-CF-000123"

    def test_strips_whitespace(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response({"results": []}))
        asyncio.get_event_loop().run_until_complete(client.search_by_party("  John Doe  "))
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["partyName"] == "John Doe"

    def test_caps_page_size_at_100(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response({"results": []}))
        asyncio.get_event_loop().run_until_complete(client.search_by_party("Test", page_size=500))
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["pageSize"] == 100

    def test_ignores_invalid_case_type_code(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response({"results": []}))
        asyncio.get_event_loop().run_until_complete(
            client.search_by_party("Test", case_type_code="INVALID")
        )
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert "caseType" not in params


class TestSearchByCaseNumber:
    def test_returns_result(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response(SAMPLE_RESULT))
        result = asyncio.get_event_loop().run_until_complete(
            client.search_by_case_number("49D01-2401-CF-000123")
        )
        assert result is not None
        assert result.case_number == "49D01-2401-CF-000123"

    def test_returns_none_on_404(self, client: MyCaseClient) -> None:
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={"detail": "Not found"}, request=req)
        client._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("Not found", request=req, response=resp_404)
        )
        result = asyncio.get_event_loop().run_until_complete(
            client.search_by_case_number("NONEXISTENT")
        )
        assert result is None

    def test_raises_on_other_errors(self, client: MyCaseClient) -> None:
        req = httpx.Request("GET", "http://test")
        resp_500 = httpx.Response(500, json={"detail": "Server error"}, request=req)
        client._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("Server error", request=req, response=resp_500)
        )
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.get_event_loop().run_until_complete(
                client.search_by_case_number("49D01-2401-CF-000123")
            )


class TestRecentFilings:
    def test_builds_date_range_params(self, client: MyCaseClient) -> None:
        client._client.get = AsyncMock(return_value=_mock_response({"results": [SAMPLE_RESULT]}))
        results = asyncio.get_event_loop().run_until_complete(
            client.recent_filings("Marion", days_back=14, case_type_code="CF")
        )
        call_kwargs = client._client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["county"] == "Marion"
        assert "dateFrom" in params
        assert "dateTo" in params
        assert params["caseType"] == "CF"
        assert len(results) == 1


class TestRetryBehaviour:
    def test_retries_on_429(self, client: MyCaseClient) -> None:
        """Client retries on 429 rate-limit responses."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.raise_for_status = MagicMock()

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.json.return_value = {"results": []}

        client._client.get = AsyncMock(side_effect=[resp_429, resp_200])
        with patch("ingestion.sources.indiana_courts.asyncio.sleep", new_callable=AsyncMock):
            results = asyncio.get_event_loop().run_until_complete(client.search_by_party("Test"))
        assert results == []
        assert client._client.get.call_count == 2

    def test_exhausts_retries(self, client: MyCaseClient) -> None:
        """Client raises RuntimeError after 3 consecutive 429s."""
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.raise_for_status = MagicMock()

        client._client.get = AsyncMock(return_value=resp_429)
        with patch("ingestion.sources.indiana_courts.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Exhausted retries"):
                asyncio.get_event_loop().run_until_complete(client.search_by_party("Test"))


class TestContextManager:
    def test_aenter_aexit(self) -> None:
        """Client can be used as an async context manager."""
        with patch.object(MyCaseClient, "__init__", lambda self, **kw: None):
            c = MyCaseClient.__new__(MyCaseClient)
            c._client = AsyncMock(spec=httpx.AsyncClient)
            c._semaphore = asyncio.Semaphore(3)

            async def _run() -> None:
                async with c:
                    pass
                c._client.aclose.assert_awaited_once()

            asyncio.get_event_loop().run_until_complete(_run())
