from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)

# Indiana public court API (Odyssey/Tyler portal)
# Docs: https://public.courts.in.gov/api (check actual base path after onboarding)
_BASE = settings.indiana_courts_api_base.rstrip("/")


@dataclass
class CourtCase:
    case_number: str
    court: str
    filing_date: date
    case_type: str          # e.g. "Civil", "Criminal", "Family"
    parties: list[str]
    summary: str
    jurisdiction: str       # e.g. "Marion County", "Hamilton County"
    documents: list[CaseDocument] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseDocument:
    doc_id: str
    case_number: str
    doc_type: str           # "Complaint", "Order", "Judgment", etc.
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

    async def __aenter__(self) -> "IndianaCourtClient":
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
                        wait = 2 ** attempt
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
