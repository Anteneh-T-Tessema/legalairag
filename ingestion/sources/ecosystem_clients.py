"""
Planned Indiana Courts ecosystem data source clients.

These clients target systems documented in docs/INDIANA_COURTS_ECOSYSTEM.md
that are marked 🔶 PLANNED. Each client is gated by a configuration flag
(empty base URL = disabled) so they are safe to deploy before data-sharing
agreements are finalised.

Sources implemented here:
- ProtectionOrderRegistryClient  — public.courts.in.gov protection orders
- CourtStatisticsClient          — in.gov/courts/research caseload data
- EFilingFeedClient              — efile.incourts.gov accepted-filings feed
- BMVClient                      — Bureau of Motor Vehicles records (requires MOU)
- ECRWClient                     — Electronic Court Record Warehouse (requires DSA)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────────────


def _sanitize(value: str) -> str:
    """Strip characters that could be used for injection or path traversal."""
    return re.sub(r"[^A-Za-z0-9\-\.\s]", "", value)


class _BaseEcosystemClient:
    """Common async HTTP client with semaphore, retry, and rate-limit handling."""

    _base_url: str
    _enabled: bool

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        max_concurrent: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._enabled = bool(base_url)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "IndyLeg/0.7.0",
                **(headers or {}),
            },
            timeout=timeout,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def __aenter__(self) -> _BaseEcosystemClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._enabled:
            raise RuntimeError(
                f"{self.__class__.__name__} is disabled (no base URL configured)"
            )
        async with self._semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.get(path, params=params)
                    if resp.status_code == 429:
                        wait = 2**attempt
                        logger.warning(
                            "rate_limited",
                            client=self.__class__.__name__,
                            path=path,
                            wait=wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[return-value]
                except httpx.HTTPStatusError:
                    raise
            raise RuntimeError(
                f"Exhausted retries for {self.__class__.__name__} {path}"
            )


# ── Protection Order Registry ─────────────────────────────────────────────────


@dataclass
class ProtectionOrder:
    """A protection order record from the statewide registry."""

    order_id: str
    order_type: str  # "Civil", "Workplace", "Child"
    county: str
    protected_party: str
    respondent: str
    issued_date: date
    expiration_date: date | None = None
    status: str = "Active"  # "Active", "Expired", "Dismissed"
    issuing_court: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ProtectionOrderRegistryClient(_BaseEcosystemClient):
    """
    Client for the Indiana Protection Order Registry.

    Provides lookup of active/expired protection orders across Indiana.
    Public safety data — no MOU required for read access to the public
    registry, though bulk access may require OCT coordination.

    See: https://www.in.gov/courts/por/
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            settings.protection_order_registry_url,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    async def search_by_respondent(
        self,
        last_name: str,
        *,
        first_name: str | None = None,
        county: str | None = None,
        status: str | None = None,
    ) -> list[ProtectionOrder]:
        """Search protection orders by respondent name."""
        params: dict[str, Any] = {"lastName": _sanitize(last_name)}
        if first_name:
            params["firstName"] = _sanitize(first_name)
        if county:
            params["county"] = _sanitize(county)
        if status:
            params["status"] = status

        data = await self._get("/api/orders/search", params=params)
        return [self._parse(item) for item in data.get("orders", [])]

    async def get_order(self, order_id: str) -> ProtectionOrder | None:
        """Fetch a specific protection order by ID."""
        try:
            data = await self._get(f"/api/orders/{_sanitize(order_id)}")
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def active_orders_by_county(
        self, county: str
    ) -> list[ProtectionOrder]:
        """List active protection orders for a given county."""
        params = {"county": _sanitize(county), "status": "Active"}
        data = await self._get("/api/orders/search", params=params)
        return [self._parse(item) for item in data.get("orders", [])]

    @staticmethod
    def _parse(data: dict[str, Any]) -> ProtectionOrder:
        exp = data.get("expirationDate")
        return ProtectionOrder(
            order_id=data.get("orderId", ""),
            order_type=data.get("orderType", "Unknown"),
            county=data.get("county", ""),
            protected_party=data.get("protectedParty", ""),
            respondent=data.get("respondent", ""),
            issued_date=date.fromisoformat(
                data.get("issuedDate", "1970-01-01")
            ),
            expiration_date=date.fromisoformat(exp) if exp else None,
            status=data.get("status", "Active"),
            issuing_court=data.get("issuingCourt", ""),
            metadata=data,
        )


# ── Court Statistics / Caseload ───────────────────────────────────────────────


@dataclass
class CaseloadReport:
    """A county-level caseload statistics report."""

    county: str
    year: int
    period: str  # "annual", "Q1", "Q2", "Q3", "Q4"
    total_filings: int
    total_dispositions: int
    pending_cases: int
    case_type_breakdown: dict[str, int] = field(default_factory=dict)
    clearance_rate: float = 0.0  # dispositions / filings
    metadata: dict[str, Any] = field(default_factory=dict)


class CourtStatisticsClient(_BaseEcosystemClient):
    """
    Client for Indiana Court Statistics / Caseload Reporting.

    Provides aggregated filing and disposition statistics by county and
    case type. Data sourced from the Office of Court Technology's
    statistical reporting system.

    See: https://www.in.gov/courts/research/
    """

    def __init__(
        self,
        max_concurrent: int = 2,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            settings.court_statistics_url,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    async def get_county_report(
        self,
        county: str,
        year: int,
        *,
        period: str = "annual",
    ) -> CaseloadReport | None:
        """Fetch a caseload report for a specific county and year."""
        params: dict[str, Any] = {
            "county": _sanitize(county),
            "year": year,
            "period": period,
        }
        try:
            data = await self._get("/api/caseload", params=params)
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def statewide_summary(
        self, year: int
    ) -> list[CaseloadReport]:
        """Fetch statewide caseload summary for all counties."""
        params: dict[str, Any] = {"year": year, "scope": "statewide"}
        data = await self._get("/api/caseload/summary", params=params)
        return [self._parse(item) for item in data.get("counties", [])]

    @staticmethod
    def _parse(data: dict[str, Any]) -> CaseloadReport:
        total_f = data.get("totalFilings", 0)
        total_d = data.get("totalDispositions", 0)
        return CaseloadReport(
            county=data.get("county", ""),
            year=data.get("year", 0),
            period=data.get("period", "annual"),
            total_filings=total_f,
            total_dispositions=total_d,
            pending_cases=data.get("pendingCases", 0),
            case_type_breakdown=data.get("caseTypeBreakdown", {}),
            clearance_rate=round(total_d / total_f, 4) if total_f else 0.0,
            metadata=data,
        )


# ── E-Filing Feed ─────────────────────────────────────────────────────────────


@dataclass
class EFilingRecord:
    """An accepted electronic filing record from efile.incourts.gov."""

    envelope_id: str
    case_number: str
    filing_type: str  # "Initial", "Subsequent", "Service"
    filed_by: str  # Attorney/firm name
    court: str
    county: str
    accepted_date: date
    document_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class EFilingFeedClient(_BaseEcosystemClient):
    """
    Client for the Indiana E-Filing portal accepted-filings feed.

    Provides a near-real-time stream of accepted electronic filings
    to support ingestion pipeline discovery. All accepted filings
    eventually appear in Odyssey/mycase.in.gov, but the e-filing feed
    provides earlier notification.

    Portal: https://efile.incourts.gov
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            settings.efiling_portal_base,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    async def recent_accepted(
        self,
        *,
        county: str | None = None,
        days_back: int = 1,
    ) -> list[EFilingRecord]:
        """Fetch recently accepted filings for ingestion discovery."""
        from datetime import timedelta

        date_from = date.today() - timedelta(days=days_back)
        params: dict[str, Any] = {
            "dateFrom": date_from.isoformat(),
            "dateTo": date.today().isoformat(),
            "status": "accepted",
        }
        if county:
            params["county"] = _sanitize(county)

        data = await self._get("/api/filings/feed", params=params)
        return [self._parse(item) for item in data.get("filings", [])]

    async def get_filing(self, envelope_id: str) -> EFilingRecord | None:
        """Look up a specific e-filing envelope."""
        try:
            data = await self._get(
                f"/api/filings/{_sanitize(envelope_id)}"
            )
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    @staticmethod
    def _parse(data: dict[str, Any]) -> EFilingRecord:
        return EFilingRecord(
            envelope_id=data.get("envelopeId", ""),
            case_number=data.get("caseNumber", ""),
            filing_type=data.get("filingType", "Unknown"),
            filed_by=data.get("filedBy", ""),
            court=data.get("court", ""),
            county=data.get("county", ""),
            accepted_date=date.fromisoformat(
                data.get("acceptedDate", "1970-01-01")
            ),
            document_count=data.get("documentCount", 0),
            metadata=data,
        )


# ── BMV Records ───────────────────────────────────────────────────────────────


@dataclass
class BMVDrivingRecord:
    """A driving record from the Indiana Bureau of Motor Vehicles."""

    record_id: str
    driver_name: str
    license_number: str
    license_status: str  # "Valid", "Suspended", "Revoked", "Expired"
    county: str
    violations: list[dict[str, Any]] = field(default_factory=list)
    points: int = 0
    last_updated: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BMVClient(_BaseEcosystemClient):
    """
    Client for the Indiana Bureau of Motor Vehicles records API.

    Requires an active Memorandum of Understanding (MOU) with the Indiana BMV.
    Used for traffic case cross-referencing and driving record lookups
    in criminal and infraction case analysis.

    This client is disabled by default (bmv_api_base = ""). Enable only
    after MOU is signed and API credentials are provisioned.
    """

    def __init__(
        self,
        max_concurrent: int = 2,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if settings.bmv_api_key:
            headers["X-Api-Key"] = settings.bmv_api_key
        super().__init__(
            settings.bmv_api_base,
            headers=headers,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    async def lookup_by_case(
        self, case_number: str
    ) -> BMVDrivingRecord | None:
        """Look up driving record linked to a traffic/criminal case."""
        params = {"caseNumber": _sanitize(case_number)}
        try:
            data = await self._get("/api/records/case-lookup", params=params)
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def lookup_by_license(
        self, license_number: str
    ) -> BMVDrivingRecord | None:
        """Look up driving record by license number."""
        sanitized = _sanitize(license_number)
        try:
            data = await self._get(f"/api/records/{sanitized}")
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    @staticmethod
    def _parse(data: dict[str, Any]) -> BMVDrivingRecord:
        updated = data.get("lastUpdated")
        return BMVDrivingRecord(
            record_id=data.get("recordId", ""),
            driver_name=data.get("driverName", ""),
            license_number=data.get("licenseNumber", ""),
            license_status=data.get("licenseStatus", "Unknown"),
            county=data.get("county", ""),
            violations=data.get("violations", []),
            points=data.get("points", 0),
            last_updated=date.fromisoformat(updated) if updated else None,
            metadata=data,
        )


# ── ECRW (Electronic Court Record Warehouse) ─────────────────────────────────


@dataclass
class ECRWRecord:
    """A historical court record from the Electronic Court Record Warehouse."""

    record_id: str
    case_number: str
    document_type: str
    court: str
    county: str
    filed_date: date
    page_count: int = 0
    download_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ECRWClient(_BaseEcosystemClient):
    """
    Client for the Electronic Court Record Warehouse (ECRW).

    The ECRW is maintained by the Indiana Office of Court Technology
    and contains bulk historical court records across all 92 counties.
    Access requires a data-sharing agreement with the Indiana Supreme Court.

    This client is disabled by default (ecrw_api_base = ""). Enable only
    after the data-sharing agreement is executed.
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            settings.ecrw_api_base,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    async def search_records(
        self,
        *,
        case_number: str | None = None,
        county: str | None = None,
        document_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ECRWRecord]:
        """Search the ECRW for historical court records."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if case_number:
            params["caseNumber"] = _sanitize(case_number)
        if county:
            params["county"] = _sanitize(county)
        if document_type:
            params["documentType"] = document_type
        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()

        data = await self._get("/api/records/search", params=params)
        return [self._parse(item) for item in data.get("records", [])]

    async def get_record(self, record_id: str) -> ECRWRecord | None:
        """Fetch a specific ECRW record."""
        try:
            data = await self._get(f"/api/records/{_sanitize(record_id)}")
            return self._parse(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def bulk_export(
        self,
        county: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[ECRWRecord]:
        """Bulk export records for a county (used for initial backfill)."""
        params: dict[str, Any] = {
            "county": _sanitize(county),
            "pageSize": 500,
        }
        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()

        data = await self._get("/api/records/bulk", params=params)
        return [self._parse(item) for item in data.get("records", [])]

    @staticmethod
    def _parse(data: dict[str, Any]) -> ECRWRecord:
        return ECRWRecord(
            record_id=data.get("recordId", ""),
            case_number=data.get("caseNumber", ""),
            document_type=data.get("documentType", "Unknown"),
            court=data.get("court", ""),
            county=data.get("county", ""),
            filed_date=date.fromisoformat(
                data.get("filedDate", "1970-01-01")
            ),
            page_count=data.get("pageCount", 0),
            download_url=data.get("downloadUrl", ""),
            metadata=data,
        )
