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

# Indiana public court API (Odyssey/Tyler portal)
# Docs: https://public.courts.in.gov/api (check actual base path after onboarding)
_BASE = settings.indiana_courts_api_base.rstrip("/")


@dataclass
class CourtCase:
    case_number: str
    court: str
    filing_date: date
    case_type: str  # e.g. "Civil", "Criminal", "Family"
    parties: list[str]
    summary: str
    jurisdiction: str  # e.g. "Marion County", "Hamilton County"
    documents: list[CaseDocument] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseDocument:
    doc_id: str
    case_number: str
    doc_type: str  # "Complaint", "Order", "Judgment", etc.
    filed_date: date
    download_url: str
    description: str = ""


class IndianaCourtClient:
    """
    Async client for the Indiana public courts API (Odyssey/Tyler portal).

    All requests are read-only (GET). Implements retry with exponential backoff
    and respects rate limits via semaphore.
    """

    def __init__(
        self,
        api_key: str = settings.indiana_courts_api_key,
        max_concurrent: int = 5,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            base_url=_BASE,
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
        )

    async def __aenter__(self) -> IndianaCourtClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def search_cases(
        self,
        *,
        query: str | None = None,
        county: str | None = None,
        case_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[CourtCase]:
        """Search public case index with optional filters."""
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if query:
            params["q"] = query
        if county:
            params["county"] = county
        if case_type:
            params["caseType"] = case_type
        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()

        data = await self._get("/cases", params=params)
        return [self._parse_case(item) for item in data.get("items", [])]

    async def get_case(self, case_number: str) -> CourtCase:
        """Fetch full case detail including document index."""
        data = await self._get(f"/cases/{_sanitize_case_number(case_number)}")
        case = self._parse_case(data)
        docs_data = await self._get(f"/cases/{_sanitize_case_number(case_number)}/documents")
        case.documents = [self._parse_document(d, case_number) for d in docs_data.get("items", [])]
        return case

    async def download_document(self, doc: CaseDocument) -> bytes:
        """Download raw document bytes (PDF/DOCX)."""
        async with self._semaphore:
            resp = await self._client.get(doc.download_url)
            resp.raise_for_status()
            return resp.content

    async def list_recent_filings(
        self,
        county: str,
        days_back: int = 7,
    ) -> list[CourtCase]:
        """Fetch filings from the past N days for streaming/near-real-time ingestion."""
        from datetime import date, timedelta

        date_from = date.today() - timedelta(days=days_back)
        return await self.search_cases(county=county, date_from=date_from, page_size=200)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.get(path, params=params)
                    if resp.status_code == 429:
                        wait = 2**attempt
                        logger.warning("rate_limited", path=path, wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[return-value]
                except httpx.HTTPStatusError as exc:
                    logger.error("http_error", path=path, status=exc.response.status_code)
                    raise
            raise RuntimeError(f"Exhausted retries for {path}")

    @staticmethod
    def _parse_case(data: dict[str, Any]) -> CourtCase:
        return CourtCase(
            case_number=data["caseNumber"],
            court=data.get("court", ""),
            filing_date=date.fromisoformat(data["filingDate"]),
            case_type=data.get("caseType", "Unknown"),
            parties=[p["name"] for p in data.get("parties", [])],
            summary=data.get("summary", ""),
            jurisdiction=data.get("county", "Indiana"),
            metadata=data,
        )

    @staticmethod
    def _parse_document(data: dict[str, Any], case_number: str) -> CaseDocument:
        return CaseDocument(
            doc_id=data["documentId"],
            case_number=case_number,
            doc_type=data.get("documentType", "Unknown"),
            filed_date=date.fromisoformat(data["filedDate"]),
            download_url=data["downloadUrl"],
            description=data.get("description", ""),
        )


def _sanitize_case_number(case_number: str) -> str:
    """Strip any characters outside alphanumeric and hyphens to prevent path traversal."""
    return re.sub(r"[^A-Za-z0-9\-]", "", case_number)


# ── mycase.in.gov — Statewide public case search ──────────────────────────

_MYCASE_BASE = settings.mycase_base_url.rstrip("/")

# All 92 Indiana counties
INDIANA_COUNTIES: list[str] = [
    "Adams", "Allen", "Bartholomew", "Benton", "Blackford", "Boone", "Brown",
    "Carroll", "Cass", "Clark", "Clay", "Clinton", "Crawford", "Daviess",
    "Dearborn", "Decatur", "DeKalb", "Delaware", "Dubois", "Elkhart",
    "Fayette", "Floyd", "Fountain", "Franklin", "Fulton", "Gibson", "Grant",
    "Greene", "Hamilton", "Hancock", "Harrison", "Hendricks", "Henry",
    "Howard", "Huntington", "Jackson", "Jasper", "Jay", "Jefferson",
    "Jennings", "Johnson", "Knox", "Kosciusko", "LaGrange", "Lake",
    "LaPorte", "Lawrence", "Madison", "Marion", "Marshall", "Martin",
    "Miami", "Monroe", "Montgomery", "Morgan", "Newton", "Noble", "Ohio",
    "Orange", "Owen", "Parke", "Perry", "Pike", "Porter", "Posey",
    "Pulaski", "Putnam", "Randolph", "Ripley", "Rush", "St. Joseph",
    "Scott", "Shelby", "Spencer", "Starke", "Steuben", "Sullivan",
    "Switzerland", "Tippecanoe", "Tipton", "Union", "Vanderburgh",
    "Vermillion", "Vigo", "Wabash", "Warren", "Warrick", "Washington",
    "Wayne", "Wells", "White", "Whitley",
]

# Indiana case type codes used across Odyssey / mycase / e-filing
CASE_TYPE_CODES: dict[str, str] = {
    "CF": "Criminal Felony",
    "CM": "Criminal Misdemeanor",
    "IF": "Infraction",
    "CT": "Civil Tort",
    "CC": "Civil Collection",
    "PL": "Civil Plenary",
    "SC": "Small Claims",
    "DR": "Domestic Relations",
    "JP": "Juvenile — CHINS/TPR",
    "JD": "Juvenile — Delinquency",
    "JS": "Juvenile — Status",
    "GU": "Guardianship",
    "ES": "Estate",
    "TR": "Trust",
    "MH": "Mental Health",
    "PO": "Protective Order",
    "AD": "Adoption",
    "MI": "Miscellaneous",
    "PC": "Post-Conviction Relief",
    "EV": "Eviction",
    "MF": "Mortgage Foreclosure",
    "XP": "Expungement",
}


@dataclass
class MyCaseSearchResult:
    case_number: str
    case_type: str
    case_type_code: str
    court: str
    county: str
    filing_date: date
    parties: list[str]
    status: str  # "Open", "Closed", "Disposed"
    judge: str
    next_hearing: date | None = None


class MyCaseClient:
    """
    Client for mycase.in.gov — Indiana's statewide public case search portal.

    Provides party-name search, case-number lookup, and recent filings
    across all 92 Indiana counties. All data is public record.

    Rate-limited to respect server capacity (default 3 concurrent requests).
    """

    def __init__(
        self,
        max_concurrent: int = settings.mycase_max_concurrent,
        timeout: float = 30.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            base_url=_MYCASE_BASE,
            headers={"Accept": "application/json", "User-Agent": "IndyLeg/0.7.0"},
            timeout=timeout,
        )

    async def __aenter__(self) -> MyCaseClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def search_by_party(
        self,
        name: str,
        *,
        county: str | None = None,
        case_type_code: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list[MyCaseSearchResult]:
        """Search mycase.in.gov by party name across all or a specific county."""
        params: dict[str, Any] = {
            "partyName": name.strip(),
            "page": page,
            "pageSize": min(page_size, 100),
        }
        if county:
            params["county"] = county
        if case_type_code and case_type_code in CASE_TYPE_CODES:
            params["caseType"] = case_type_code

        data = await self._get("/search/party", params=params)
        return [self._parse_result(item) for item in data.get("results", [])]

    async def search_by_case_number(self, case_number: str) -> MyCaseSearchResult | None:
        """Look up a specific case by its case number."""
        sanitized = _sanitize_case_number(case_number)
        try:
            data = await self._get(f"/case/{sanitized}")
            return self._parse_result(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def recent_filings(
        self,
        county: str,
        *,
        case_type_code: str | None = None,
        days_back: int = 7,
    ) -> list[MyCaseSearchResult]:
        """Fetch recent filings for a given county (for near-real-time ingestion)."""
        from datetime import timedelta

        date_from = date.today() - timedelta(days=days_back)
        params: dict[str, Any] = {
            "county": county,
            "dateFrom": date_from.isoformat(),
            "dateTo": date.today().isoformat(),
        }
        if case_type_code and case_type_code in CASE_TYPE_CODES:
            params["caseType"] = case_type_code

        data = await self._get("/search/recent", params=params)
        return [self._parse_result(item) for item in data.get("results", [])]

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._semaphore:
            for attempt in range(3):
                try:
                    resp = await self._client.get(path, params=params)
                    if resp.status_code == 429:
                        wait = 2**attempt
                        logger.warning("mycase_rate_limited", path=path, wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[return-value]
                except httpx.HTTPStatusError as exc:
                    logger.error("mycase_http_error", path=path, status=exc.response.status_code)
                    raise
            raise RuntimeError(f"Exhausted retries for mycase {path}")

    @staticmethod
    def _parse_result(data: dict[str, Any]) -> MyCaseSearchResult:
        next_hearing = None
        if data.get("nextHearing"):
            next_hearing = date.fromisoformat(data["nextHearing"])
        return MyCaseSearchResult(
            case_number=data.get("caseNumber", ""),
            case_type=CASE_TYPE_CODES.get(
                data.get("caseTypeCode", ""), data.get("caseType", "Unknown")
            ),
            case_type_code=data.get("caseTypeCode", ""),
            court=data.get("court", ""),
            county=data.get("county", ""),
            filing_date=date.fromisoformat(data.get("filingDate", "1970-01-01")),
            parties=[p.get("name", "") for p in data.get("parties", [])],
            status=data.get("caseStatus", "Unknown"),
            judge=data.get("judge", ""),
            next_hearing=next_hearing,
        )
