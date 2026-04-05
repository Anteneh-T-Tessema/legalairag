from __future__ import annotations

import re
from dataclasses import dataclass

from config.logging import get_logger

logger = get_logger(__name__)

# Jurisdiction name normalisations → canonical county names
_COUNTY_ALIASES: dict[str, str] = {
    "marion": "Marion County",
    "hamilton": "Hamilton County",
    "hendricks": "Hendricks County",
    "johnson": "Johnson County",
    "boone": "Boone County",
    "allen": "Allen County",
    "vanderburgh": "Vanderburgh County",
    "tippecanoe": "Tippecanoe County",
    "lake": "Lake County",
    "monroe": "Monroe County",
}

# Legal case type keywords → canonical type
_CASE_TYPE_KEYWORDS: dict[str, str] = {
    "criminal": "Criminal",
    "felony": "Criminal",
    "misdemeanor": "Criminal",
    "civil": "Civil",
    "small claims": "Small Claims",
    "family": "Family",
    "juvenile": "Juvenile",
    "estate": "Probate",
    "probate": "Probate",
    "contract": "Civil",
    "tort": "Civil",
}

_CITATION_RE = re.compile(
    r"(?:Ind(?:iana)?\.?\s*Code\s*§\s*[\d\-\.]+|I\.C\.\s*§\s*[\d\-\.]+)",
    re.IGNORECASE,
)


@dataclass
class ParsedQuery:
    raw: str
    normalized: str
    jurisdiction: str | None
    case_type: str | None
    citations_mentioned: list[str]
    keywords: list[str]


def parse_legal_query(query: str) -> ParsedQuery:
    """
    Extract structured signals from a free-text legal query:
    - jurisdiction / county mentions
    - case type hints
    - explicit statutory citations pasted inline
    - general keywords for BM25

    This pre-processing step improves both retrieval precision and
    the downstream prompt construction for grounded generation.
    """
    lower = query.lower()

    jurisdiction = _detect_jurisdiction(lower)
    case_type = _detect_case_type(lower)
    citations = _CITATION_RE.findall(query)
    keywords = _extract_keywords(query)
    normalized = _normalize_query(query)

    parsed = ParsedQuery(
        raw=query,
        normalized=normalized,
        jurisdiction=jurisdiction,
        case_type=case_type,
        citations_mentioned=[c.strip() for c in citations],
        keywords=keywords,
    )

    logger.debug(
        "query_parsed",
        jurisdiction=jurisdiction,
        case_type=case_type,
        citations=citations,
    )
    return parsed


def _detect_jurisdiction(lower: str) -> str | None:
    for alias, canonical in _COUNTY_ALIASES.items():
        if alias in lower:
            return canonical
    # Generic Indiana mention
    if "indiana" in lower or " ind " in lower or "in court" in lower:
        return "Indiana"
    return None


def _detect_case_type(lower: str) -> str | None:
    for keyword, canonical in _CASE_TYPE_KEYWORDS.items():
        if keyword in lower:
            return canonical
    return None


def _extract_keywords(query: str) -> list[str]:
    """Simple keyword extraction: remove stopwords, return unique tokens."""
    stopwords = {
        "the", "a", "an", "is", "in", "of", "for", "on", "at", "to",
        "and", "or", "what", "how", "when", "where", "who", "does",
        "did", "can", "will", "my", "i", "me",
    }
    tokens = re.findall(r"\b[a-zA-Z]{3,}\b", query)
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        lower_t = t.lower()
        if lower_t not in stopwords and lower_t not in seen:
            seen.add(lower_t)
            result.append(lower_t)
    return result


def _normalize_query(query: str) -> str:
    """Light normalization: collapse whitespace, strip trailing punctuation."""
    q = re.sub(r"\s+", " ", query).strip()
    q = q.rstrip("?.,;:")
    return q
