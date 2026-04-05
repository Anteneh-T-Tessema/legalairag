"""Unit tests for ecosystem data source clients (planned Indiana Courts sources).

Tests cover: _BaseEcosystemClient shared logic, ProtectionOrderRegistryClient,
CourtStatisticsClient, EFilingFeedClient, BMVClient, ECRWClient.

All HTTP I/O is mocked — no network calls are made.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ingestion.sources.ecosystem_clients import (
    BMVClient,
    BMVDrivingRecord,
    CaseloadReport,
    CourtStatisticsClient,
    ECRWClient,
    ECRWRecord,
    EFilingFeedClient,
    EFilingRecord,
    ProtectionOrder,
    ProtectionOrderRegistryClient,
    _sanitize,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_response(
    json_data: dict, status_code: int = 200
) -> httpx.Response:
    req = httpx.Request("GET", "http://test")
    return httpx.Response(
        status_code=status_code, json=json_data, request=req
    )


def _run(coro):  # noqa: ANN001, ANN201
    """Shortcut for running a coroutine in the default event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_client(cls, base_url: str = "http://test"):
    """Create a client instance with mocked httpx transport."""
    with patch.object(cls, "__init__", lambda self, **kw: None):
        c = cls.__new__(cls)
        c._base_url = base_url
        c._enabled = bool(base_url)
        c._semaphore = asyncio.Semaphore(3)
        c._client = AsyncMock(spec=httpx.AsyncClient)
        return c


# ── _sanitize ─────────────────────────────────────────────────────────────────


class TestSanitize:
    def test_alphanumeric_unchanged(self) -> None:
        assert _sanitize("Marion") == "Marion"

    def test_strips_slashes(self) -> None:
        assert _sanitize("../../etc/passwd") == "....etcpasswd"

    def test_strips_semicolons(self) -> None:
        assert _sanitize("test; DROP TABLE") == "test DROP TABLE"

    def test_preserves_dots_hyphens_spaces(self) -> None:
        assert _sanitize("St. Joseph-County 1") == "St. Joseph-County 1"


# ── Base client disabled behaviour ────────────────────────────────────────────


class TestBaseClientDisabled:
    def test_disabled_when_no_base_url(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient, base_url="")
        assert c.enabled is False

    def test_raises_on_get_when_disabled(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient, base_url="")
        with pytest.raises(RuntimeError, match="disabled"):
            _run(c._get("/anything"))


# ── ProtectionOrderRegistryClient ─────────────────────────────────────────────

SAMPLE_PO = {
    "orderId": "PO-2024-001",
    "orderType": "Civil",
    "county": "Marion",
    "protectedParty": "Jane Doe",
    "respondent": "John Smith",
    "issuedDate": "2024-01-10",
    "expirationDate": "2025-01-10",
    "status": "Active",
    "issuingCourt": "Marion Superior Court 5",
}


class TestProtectionOrderRegistryClient:
    def test_parse_full(self) -> None:
        result = ProtectionOrderRegistryClient._parse(SAMPLE_PO)
        assert isinstance(result, ProtectionOrder)
        assert result.order_id == "PO-2024-001"
        assert result.order_type == "Civil"
        assert result.county == "Marion"
        assert result.issued_date == date(2024, 1, 10)
        assert result.expiration_date == date(2025, 1, 10)
        assert result.status == "Active"

    def test_parse_no_expiration(self) -> None:
        data = {**SAMPLE_PO}
        del data["expirationDate"]
        result = ProtectionOrderRegistryClient._parse(data)
        assert result.expiration_date is None

    def test_search_by_respondent(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient)
        c._client.get = AsyncMock(
            return_value=_mock_response({"orders": [SAMPLE_PO]})
        )
        results = _run(
            c.search_by_respondent("Smith", county="Marion")
        )
        assert len(results) == 1
        assert results[0].respondent == "John Smith"

    def test_get_order_returns_none_on_404(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient)
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=req, response=resp_404
            )
        )
        result = _run(c.get_order("NONEXISTENT"))
        assert result is None


# ── CourtStatisticsClient ────────────────────────────────────────────────────

SAMPLE_CASELOAD = {
    "county": "Marion",
    "year": 2024,
    "period": "annual",
    "totalFilings": 45000,
    "totalDispositions": 42000,
    "pendingCases": 8500,
    "caseTypeBreakdown": {"CF": 5000, "CM": 12000, "CT": 3000},
}


class TestCourtStatisticsClient:
    def test_parse(self) -> None:
        result = CourtStatisticsClient._parse(SAMPLE_CASELOAD)
        assert isinstance(result, CaseloadReport)
        assert result.county == "Marion"
        assert result.total_filings == 45000
        assert result.clearance_rate == pytest.approx(0.9333, abs=0.001)
        assert result.case_type_breakdown["CF"] == 5000

    def test_clearance_rate_zero_filings(self) -> None:
        data = {**SAMPLE_CASELOAD, "totalFilings": 0}
        result = CourtStatisticsClient._parse(data)
        assert result.clearance_rate == 0.0

    def test_get_county_report(self) -> None:
        c = _make_client(CourtStatisticsClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(SAMPLE_CASELOAD)
        )
        result = _run(c.get_county_report("Marion", 2024))
        assert result is not None
        assert result.county == "Marion"

    def test_get_county_report_404(self) -> None:
        c = _make_client(CourtStatisticsClient)
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=req, response=resp_404
            )
        )
        result = _run(c.get_county_report("Nonexistent", 2024))
        assert result is None

    def test_statewide_summary(self) -> None:
        c = _make_client(CourtStatisticsClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(
                {"counties": [SAMPLE_CASELOAD, SAMPLE_CASELOAD]}
            )
        )
        results = _run(c.statewide_summary(2024))
        assert len(results) == 2


# ── EFilingFeedClient ─────────────────────────────────────────────────────────

SAMPLE_EFILING = {
    "envelopeId": "ENV-2024-001",
    "caseNumber": "49D01-2401-CT-000789",
    "filingType": "Initial",
    "filedBy": "Smith & Associates",
    "court": "Marion Superior Court 1",
    "county": "Marion",
    "acceptedDate": "2024-03-15",
    "documentCount": 3,
}


class TestEFilingFeedClient:
    def test_parse(self) -> None:
        result = EFilingFeedClient._parse(SAMPLE_EFILING)
        assert isinstance(result, EFilingRecord)
        assert result.envelope_id == "ENV-2024-001"
        assert result.filing_type == "Initial"
        assert result.document_count == 3
        assert result.accepted_date == date(2024, 3, 15)

    def test_recent_accepted(self) -> None:
        c = _make_client(EFilingFeedClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(
                {"filings": [SAMPLE_EFILING]}
            )
        )
        results = _run(c.recent_accepted(county="Marion", days_back=7))
        assert len(results) == 1
        assert results[0].case_number == "49D01-2401-CT-000789"

    def test_get_filing_returns_none_on_404(self) -> None:
        c = _make_client(EFilingFeedClient)
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=req, response=resp_404
            )
        )
        assert _run(c.get_filing("NONEXISTENT")) is None


# ── BMVClient ─────────────────────────────────────────────────────────────────

SAMPLE_BMV = {
    "recordId": "BMV-001",
    "driverName": "John Doe",
    "licenseNumber": "1234-5678-9012",
    "licenseStatus": "Valid",
    "county": "Marion",
    "violations": [{"code": "52-01", "description": "Speeding"}],
    "points": 4,
    "lastUpdated": "2024-02-01",
}


class TestBMVClient:
    def test_parse_full(self) -> None:
        result = BMVClient._parse(SAMPLE_BMV)
        assert isinstance(result, BMVDrivingRecord)
        assert result.driver_name == "John Doe"
        assert result.license_status == "Valid"
        assert result.points == 4
        assert result.last_updated == date(2024, 2, 1)
        assert len(result.violations) == 1

    def test_parse_no_updated_date(self) -> None:
        data = {k: v for k, v in SAMPLE_BMV.items() if k != "lastUpdated"}
        result = BMVClient._parse(data)
        assert result.last_updated is None

    def test_lookup_by_case(self) -> None:
        c = _make_client(BMVClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(SAMPLE_BMV)
        )
        result = _run(c.lookup_by_case("49D01-2401-IF-000001"))
        assert result is not None
        assert result.driver_name == "John Doe"

    def test_lookup_by_case_404(self) -> None:
        c = _make_client(BMVClient)
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=req, response=resp_404
            )
        )
        assert _run(c.lookup_by_case("NONEXISTENT")) is None

    def test_lookup_by_license(self) -> None:
        c = _make_client(BMVClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(SAMPLE_BMV)
        )
        result = _run(c.lookup_by_license("1234-5678-9012"))
        assert result is not None
        assert result.license_number == "1234-5678-9012"

    def test_disabled_when_no_base(self) -> None:
        c = _make_client(BMVClient, base_url="")
        assert c.enabled is False


# ── ECRWClient ────────────────────────────────────────────────────────────────

SAMPLE_ECRW = {
    "recordId": "ECRW-12345",
    "caseNumber": "49D01-2010-CF-045678",
    "documentType": "Judgment",
    "court": "Marion Superior Court 1",
    "county": "Marion",
    "filedDate": "2010-08-15",
    "pageCount": 12,
    "downloadUrl": "https://ecrw.in.gov/records/ECRW-12345.pdf",
}


class TestECRWClient:
    def test_parse(self) -> None:
        result = ECRWClient._parse(SAMPLE_ECRW)
        assert isinstance(result, ECRWRecord)
        assert result.record_id == "ECRW-12345"
        assert result.document_type == "Judgment"
        assert result.page_count == 12
        assert result.filed_date == date(2010, 8, 15)

    def test_search_records(self) -> None:
        c = _make_client(ECRWClient)
        c._client.get = AsyncMock(
            return_value=_mock_response(
                {"records": [SAMPLE_ECRW, SAMPLE_ECRW]}
            )
        )
        results = _run(
            c.search_records(county="Marion", document_type="Judgment")
        )
        assert len(results) == 2

    def test_get_record_404(self) -> None:
        c = _make_client(ECRWClient)
        req = httpx.Request("GET", "http://test")
        resp_404 = httpx.Response(404, json={}, request=req)
        c._client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not found", request=req, response=resp_404
            )
        )
        assert _run(c.get_record("NONEXISTENT")) is None

    def test_bulk_export(self) -> None:
        c = _make_client(ECRWClient)
        c._client.get = AsyncMock(
            return_value=_mock_response({"records": [SAMPLE_ECRW]})
        )
        results = _run(c.bulk_export("Marion"))
        assert len(results) == 1

    def test_disabled_when_no_base(self) -> None:
        c = _make_client(ECRWClient, base_url="")
        assert c.enabled is False


# ── Retry behaviour (shared base) ────────────────────────────────────────────


class TestBaseRetry:
    def test_retries_on_429(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient)
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.raise_for_status = MagicMock()
        resp_200.json.return_value = {"orders": []}

        c._client.get = AsyncMock(side_effect=[resp_429, resp_200])
        with patch(
            "ingestion.sources.ecosystem_clients.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            results = _run(
                c.search_by_respondent("Test")
            )
        assert results == []
        assert c._client.get.call_count == 2

    def test_exhausts_retries(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient)
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        c._client.get = AsyncMock(return_value=resp_429)
        with patch(
            "ingestion.sources.ecosystem_clients.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with pytest.raises(RuntimeError, match="Exhausted retries"):
                _run(c.search_by_respondent("Test"))


# ── Context manager ──────────────────────────────────────────────────────────


class TestContextManager:
    def test_aenter_aexit(self) -> None:
        c = _make_client(ProtectionOrderRegistryClient)
        _run(c.__aenter__())
        _run(c.__aexit__(None, None, None))
        c._client.aclose.assert_awaited_once()
