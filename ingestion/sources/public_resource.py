"""
Public legal data ingestion from two open sources:

1. CourtListener REST API (Free Law Project) — Indiana state court opinions
   Endpoint: https://www.courtlistener.com/api/rest/v4/opinions/
   Indiana Supreme Court cluster_id: 8985
   Indiana Court of Appeals cluster_id: 8984
   Documentation: https://www.courtlistener.com/api/rest-info/

2. law.resource.org bulk opinions — Federal Reporter (7th Circuit covers Indiana)
   Base: https://law.resource.org/pub/us/case/reporter/
   Relevant: F3/ (Federal Reporter 3rd, most recent), F2/, F/
   These are public domain HTML files, freely downloadable.

Both sources expose public-domain government documents — no copyright restrictions.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

# ── CourtListener constants ────────────────────────────────────────────────────
_CL_BASE = "https://www.courtlistener.com/api/rest/v4"

# Indiana court cluster IDs in CourtListener
# Source: https://www.courtlistener.com/api/rest/v4/courts/?id=ind
_CL_COURTS: dict[str, str] = {
    "ind": "Indiana Supreme Court",
    "indctapp": "Indiana Court of Appeals",
    "indtc": "Indiana Tax Court",
    "ca7": "7th Circuit Court of Appeals",  # Federal — covers Indiana
}

# ── law.resource.org constants ─────────────────────────────────────────────────
_LRO_BASE = "https://law.resource.org/pub/us/case/reporter"
# 7th Circuit directories within the F-series reporters
_LRO_SEVENTH_CIRCUIT_DIRS = ["F3", "F2"]  # Most recent first


@dataclass
class PublicLegalOpinion:
    """Normalized representation of a court opinion from any public source."""

    opinion_id: str  # Stable, source-prefixed ID e.g. "cl-12345" or "lro-F3-123"
    source: str  # "courtlistener" | "law_resource_org"
    court: str  # Canonical court name
    # "supreme" | "appeals" | "trial" | "federal_circuit" | "federal_supreme"
    court_level: str
    case_name: str
    docket_number: str
    date_filed: date
    jurisdiction: str  # "Indiana" | "Federal/7th Circuit"
    text: str  # Full opinion text (plain)
    citations_out: list[str]  # Citations this opinion makes
    url: str  # Canonical source URL
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        return self.opinion_id

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:16]


class CourtListenerClient:
    """
    Async client for CourtListener REST API v4.

    Retrieves Indiana court opinions (state + 7th Circuit) with pagination,
    rate limiting, and structured metadata extraction.

    Authentication: CourtListener allows unauthenticated read access (100 req/day).
    With an API token, limits increase substantially. Configure via settings.
    """

    def __init__(
        self,
        api_token: str = settings.courtlistener_api_token,
        max_concurrent: int = 3,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            base_url=_CL_BASE,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> CourtListenerClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def fetch_opinions(
        self,
        court_id: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        page_size: int = 20,
        max_pages: int = 5,
    ) -> list[PublicLegalOpinion]:
        """
        Paginate through opinions for a given court.

        Parameters
        ----------
        court_id:   CourtListener court identifier (e.g. "ind", "ca7")
        date_from:  Only return opinions filed on/after this date
        date_to:    Only return opinions filed on/before this date
        page_size:  Results per page (max 100 per API docs)
        max_pages:  Safety cap on pagination depth
        """
        opinions: list[PublicLegalOpinion] = []
        params: dict[str, Any] = {
            "court": court_id,
            "page_size": min(page_size, 100),
            "order_by": "-date_filed",
            "format": "json",
        }
        if date_from:
            params["date_filed__gte"] = date_from.isoformat()
        if date_to:
            params["date_filed__lte"] = date_to.isoformat()

        url = "/opinions/"
        pages_fetched = 0

        while url and pages_fetched < max_pages:
            async with self._semaphore:
                try:
                    page_params = params if pages_fetched == 0 else None
                    resp = await self._client.get(url, params=page_params)
                    if resp.status_code == 429:
                        wait = 2**pages_fetched
                        logger.warning("courtlistener_rate_limited", wait=wait)
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPError as exc:
                    logger.error("courtlistener_http_error", error=str(exc))
                    break

            court_name = _CL_COURTS.get(court_id, court_id)
            for item in data.get("results", []):
                opinion = self._parse_opinion(item, court_id, court_name)
                if opinion:
                    opinions.append(opinion)

            url = data.get("next")  # CourtListener provides absolute URL for next page
            params = {}  # params encoded in `next` URL
            pages_fetched += 1

            logger.info(
                "courtlistener_page",
                court=court_id,
                page=pages_fetched,
                fetched=len(opinions),
            )

        return opinions

    async def fetch_indiana_opinions(
        self,
        *,
        include_federal: bool = True,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[PublicLegalOpinion]:
        """Convenience: fetch opinions from all Indiana-relevant courts concurrently."""
        courts = list(_CL_COURTS.keys())
        if not include_federal:
            courts = [c for c in courts if c != "ca7"]

        tasks = [
            self.fetch_opinions(court_id, date_from=date_from, date_to=date_to)
            for court_id in courts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_opinions: list[PublicLegalOpinion] = []
        for court_id, result in zip(courts, results):  # noqa: B905
            if isinstance(result, BaseException):
                logger.error("courtlistener_court_error", court=court_id, error=str(result))
            else:
                all_opinions.extend(result)

        logger.info(
            "courtlistener_total",
            total_opinions=len(all_opinions),
            courts=courts,
        )
        return all_opinions

    @staticmethod
    def _parse_opinion(
        data: dict[str, Any],
        court_id: str,
        court_name: str,
    ) -> PublicLegalOpinion | None:
        """Parse a single CourtListener opinion JSON record."""
        try:
            # Extract text — CourtListener provides multiple formats; prefer plain_text
            text = (
                data.get("plain_text")
                or _strip_html(data.get("html_with_citations", ""))
                or _strip_html(data.get("html", ""))
                or ""
            )
            if len(text) < 100:
                return None  # Skip empty/stub opinions

            filed_raw = data.get("date_filed") or data.get("date_created", "")[:10]
            filed = date.fromisoformat(filed_raw) if filed_raw else date.today()

            # Extract citations from CourtListener citation objects
            citations_out: list[str] = []
            for cite in data.get("citations", []):
                if isinstance(cite, dict):
                    citations_out.append(cite.get("cite", ""))
                elif isinstance(cite, str):
                    citations_out.append(cite)

            court_level = _classify_court_level(court_id)
            jurisdiction = "Federal/7th Circuit" if court_id == "ca7" else "Indiana"

            # Use cluster URL as canonical reference
            cluster_url = data.get("cluster", "") or data.get("absolute_url", "")
            if cluster_url and not cluster_url.startswith("http"):
                cluster_url = f"https://www.courtlistener.com{cluster_url}"

            return PublicLegalOpinion(
                opinion_id=f"cl-{data['id']}",
                source="courtlistener",
                court=court_name,
                court_level=court_level,
                case_name=data.get("case_name", "Unknown Case"),
                docket_number=(
                    data["docket"].get("docket_number", "")
                    if isinstance(data.get("docket"), dict)
                    else ""
                ),
                date_filed=filed,
                jurisdiction=jurisdiction,
                text=text,
                citations_out=[c for c in citations_out if c],
                url=cluster_url,
                metadata={
                    "cl_id": data["id"],
                    "court_id": court_id,
                    "author": data.get("author_str", ""),
                    "per_curiam": data.get("per_curiam", False),
                    "type": data.get("type", ""),
                },
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("courtlistener_parse_error", error=str(exc))
            return None


class LawResourceOrgClient:
    """
    Client for law.resource.org bulk opinion access.

    Downloads Federal Reporter HTML files for cases from the 7th Circuit
    (which has jurisdiction over Indiana federal district courts).

    The repository is organized as:
      /pub/us/case/reporter/F3/<volume>/<volume>.F3.<page>.html

    Each HTML page is a single court opinion in the public domain.
    """

    def __init__(self, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=_LRO_BASE,
            headers={"User-Agent": "IndyLeg-Legal-RAG/0.1 (educational/research)"},
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> LawResourceOrgClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def list_volumes(self, reporter_series: str = "F3") -> list[str]:
        """List available volume directories for a reporter series."""
        try:
            resp = await self._client.get(f"/{reporter_series}/")
            resp.raise_for_status()
            # Parse directory listing (Apache-style HTML index)
            return _parse_dir_listing(resp.text)
        except httpx.HTTPError as exc:
            logger.error("lro_list_volumes_error", series=reporter_series, error=str(exc))
            return []

    async def fetch_opinion_html(self, reporter: str, volume: str, filename: str) -> str:
        """Fetch a single opinion HTML file from law.resource.org."""
        path = f"/{reporter}/{volume}/{filename}"
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            logger.warning("lro_fetch_error", path=path, error=str(exc))
            return ""

    async def fetch_indiana_seventh_circuit_samples(
        self,
        reporter_series: str = "F3",
        max_volumes: int = 3,
        opinions_per_volume: int = 10,
    ) -> list[PublicLegalOpinion]:
        """
        Fetch a sample of 7th Circuit opinions that may involve Indiana.

        In production, this would be run as a large batch job with full volume
        traversal. Here we sample recent volumes.
        """
        volumes = await self.list_volumes(reporter_series)
        # Take the most recent volumes (highest numbers come last)
        recent_volumes = sorted(volumes, reverse=True)[:max_volumes]

        all_opinions: list[PublicLegalOpinion] = []
        for volume in recent_volumes:
            files = await self._list_opinion_files(reporter_series, volume)
            for fname in files[:opinions_per_volume]:
                html = await self.fetch_opinion_html(reporter_series, volume, fname)
                if not html:
                    continue
                opinion = _parse_lro_opinion_html(
                    html,
                    reporter=reporter_series,
                    volume=volume,
                    filename=fname,
                )
                if opinion:
                    all_opinions.append(opinion)

        logger.info(
            "lro_fetched",
            reporter=reporter_series,
            volumes=len(recent_volumes),
            opinions=len(all_opinions),
        )
        return all_opinions

    async def _list_opinion_files(self, reporter: str, volume: str) -> list[str]:
        try:
            resp = await self._client.get(f"/{reporter}/{volume}/")
            resp.raise_for_status()
            files = _parse_dir_listing(resp.text)
            return [f for f in files if f.endswith(".html") and not f.startswith("0_")]
        except httpx.HTTPError:
            return []


# ── Indiana IGA Statutes Source ────────────────────────────────────────────────

_IGA_BASE = "https://iga.in.gov"
_IGA_STATUTE_API = "https://iga.in.gov/api/20231116/mobile-sdk/laws/indiana-code"


@dataclass
class IndianaStatute:
    """A section of the Indiana Code, fetched from iga.in.gov."""

    statute_id: str  # e.g. "ic-35-42-1-1"
    title: str  # e.g. "35-42-1-1"
    full_citation: str  # e.g. "Ind. Code § 35-42-1-1"
    subject: str  # e.g. "Murder"
    article: str
    chapter: str
    section_text: str
    effective_date: date | None
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        return self.statute_id


class IndianaCodeClient:
    """
    Fetches Indiana Code sections from the Indiana General Assembly's public API.

    The IGA exposes Indiana statutes as structured JSON. This is the authoritative
    source for current statutory text — more reliable than scraping or PDFs.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=_IGA_BASE,
            headers={
                "Accept": "application/json",
                "User-Agent": "IndyLeg-Legal-RAG/0.1",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> IndianaCodeClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def fetch_title(self, title_number: int) -> list[IndianaStatute]:
        """
        Fetch all sections under an Indiana Code title.

        Example: title_number=35 → Criminal Law and Procedure
        """
        url = f"/api/20231116/mobile-sdk/laws/indiana-code/titles/{title_number}"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            statutes: list[IndianaStatute] = []
            for article in data.get("articles", []):
                for chapter in article.get("chapters", []):
                    for section in chapter.get("sections", []):
                        statute = self._parse_statute(
                            section,
                            title=str(title_number),
                            article=article.get("number", ""),
                            chapter=chapter.get("number", ""),
                        )
                        if statute:
                            statutes.append(statute)
            logger.info("iga_title_fetched", title=title_number, sections=len(statutes))
            return statutes
        except httpx.HTTPError as exc:
            logger.error("iga_fetch_error", title=title_number, error=str(exc))
            return []

    async def fetch_section(
        self,
        title: int,
        article: int,
        chapter: int,
        section: int,
    ) -> IndianaStatute | None:
        """Fetch a single Indiana Code section by citation coordinates."""
        url = (
            f"/api/20231116/mobile-sdk/laws/indiana-code"
            f"/titles/{title}/articles/{article}"
            f"/chapters/{chapter}/sections/{section}"
        )
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return self._parse_statute(
                data,
                title=str(title),
                article=str(article),
                chapter=str(chapter),
            )
        except httpx.HTTPError as exc:
            logger.error("iga_section_fetch_error", url=url, error=str(exc))
            return None

    @staticmethod
    def _parse_statute(
        data: dict[str, Any],
        title: str,
        article: str,
        chapter: str,
    ) -> IndianaStatute | None:
        try:
            sec_num = data.get("number", "")
            full_cite = f"Ind. Code § {title}-{article}-{chapter}-{sec_num}"
            statute_id = f"ic-{title}-{article}-{chapter}-{sec_num}"

            effective_str = data.get("effectiveDate") or data.get("effective_date")
            effective: date | None = None
            if effective_str:
                try:
                    effective = date.fromisoformat(effective_str[:10])
                except ValueError:
                    pass

            return IndianaStatute(
                statute_id=statute_id,
                title=title,
                full_citation=full_cite,
                subject=data.get("title", "") or data.get("subject", ""),
                article=article,
                chapter=chapter,
                section_text=data.get("text", "") or data.get("sectionText", ""),
                effective_date=effective,
                url=f"https://iga.in.gov/laws/indiana-code/title/{title}/article/{article}/chapter/{chapter}/section/{sec_num}",
                metadata={"raw": data},
            )
        except (KeyError, TypeError) as exc:
            logger.warning("iga_parse_error", error=str(exc))
            return None


# ── Helpers ────────────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s{2,}")
_DIR_LISTING_HREF_RE = re.compile(r'href="([^"?#]+)"')
_INDIANA_INDICATOR_RE = re.compile(
    r"\bIndiana\b|\bInd\.?\b|\bS\.D\. Ind\b|\bN\.D\. Ind\b|\bIndianapolis\b",
    re.IGNORECASE,
)


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _parse_dir_listing(html: str) -> list[str]:
    """Extract hrefs from an Apache-style directory listing, skip parent links."""
    hrefs = _DIR_LISTING_HREF_RE.findall(html)
    return [h.rstrip("/") for h in hrefs if h not in ("../", "/", "./") and not h.startswith("?")]


def _classify_court_level(court_id: str) -> str:
    mapping = {
        "ind": "supreme",
        "indctapp": "appeals",
        "indtc": "trial",
        "ca7": "federal_circuit",
        "scotus": "federal_supreme",
    }
    return mapping.get(court_id, "unknown")


def _parse_lro_opinion_html(
    html: str,
    reporter: str,
    volume: str,
    filename: str,
) -> PublicLegalOpinion | None:
    """
    Parse a Law.Resource.Org Federal Reporter HTML opinion.

    Extract case name, court, date, and text from the HTML structure.
    These files follow a loose format — we extract what we can reliably.
    """
    text = _strip_html(html)
    if len(text) < 200:
        return None

    # Heuristic: only include if Indiana is mentioned (7th Cir covers 3 states)
    if not _INDIANA_INDICATOR_RE.search(text[:2000]):
        return None

    # Try to extract case name from first non-empty lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    case_name = lines[0] if lines else "Unknown Case"

    # Try to extract date
    date_match = re.search(r"\b(\d{4})\b", text[:500])
    year = int(date_match.group(1)) if date_match else 2000
    filed = date(max(1900, min(year, date.today().year)), 1, 1)

    # Extract citations mentioned
    citations = re.findall(
        r"\d+\s+(?:F\.2d|F\.3d|F\.4th|U\.S\.)\s+\d+",
        text,
    )

    opinion_id = f"lro-{reporter}-{volume}-{filename.replace('.html', '').replace('.', '-')}"

    return PublicLegalOpinion(
        opinion_id=opinion_id,
        source="law_resource_org",
        court="7th Circuit Court of Appeals",
        court_level="federal_circuit",
        case_name=case_name,
        docket_number="",
        date_filed=filed,
        jurisdiction="Federal/7th Circuit",
        text=text,
        citations_out=list(set(citations)),
        url=f"{_LRO_BASE}/{reporter}/{volume}/{filename}",
        metadata={
            "reporter": reporter,
            "volume": volume,
            "filename": filename,
        },
    )
