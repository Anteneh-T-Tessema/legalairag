from __future__ import annotations

import re
from dataclasses import dataclass, field

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

# Query type classification signals
# "citation_lookup" → exact statutory/case reference → favor BM25
# "semantic" → conceptual question → favor dense vector
# "hybrid" → both signals present
_CITATION_LOOKUP_SIGNALS = re.compile(
    r"""
    (?:
        Ind(?:iana)?\.?\s*Code\s*§\s*[\d\-\.]+   # Indiana Code citation
        | I\.C\.\s*§\s*[\d\-\.]+                  # I.C. § citation
        | \d+\s+(?:F\.|Ind\.|N\.E\.)\s*\d+        # Reporter citation
        | [A-Z][a-z]+\s+v\.\s+[A-Z][a-z]+         # Case name (v.)
        | §\s*[\d\-\.]+                             # Bare § reference
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)
_SEMANTIC_SIGNALS = re.compile(
    r"\b(?:what|how|why|when|explain|define|describe|analyze|summarize|is\s+it)\b",
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
    query_type: str = "hybrid"         # "citation_lookup" | "semantic" | "hybrid"
    bm25_weight: float = 0.5           # Suggested BM25 weight for RRF (0=all vector, 1=all BM25)
    authority_alpha: float = 0.30      # Suggested authority blend alpha
    temporal_filter: bool = False      # Whether to apply temporal validity filter


def parse_legal_query(query: str) -> ParsedQuery:
    """
    Extract structured signals from a free-text legal query:
    - jurisdiction / county mentions
    - case type hints
    - explicit statutory citations pasted inline
    - query type classification (citation_lookup vs semantic)
    - adaptive weights for BM25 / vector / authority blending

    This pre-processing step improves both retrieval precision and
    the downstream prompt construction for grounded generation.
    """
    lower = query.lower()

    jurisdiction = _detect_jurisdiction(lower)
    case_type = _detect_case_type(lower)
    citations = _CITATION_RE.findall(query)
    keywords = _extract_keywords(query)
    normalized = _normalize_query(query)
    query_type, bm25_weight, authority_alpha = _classify_query(query)
    temporal_filter = _needs_temporal_filter(lower)

    parsed = ParsedQuery(
        raw=query,
        normalized=normalized,
        jurisdiction=jurisdiction,
        case_type=case_type,
        citations_mentioned=[c.strip() for c in citations],
        keywords=keywords,
        query_type=query_type,
        bm25_weight=bm25_weight,
        authority_alpha=authority_alpha,
        temporal_filter=temporal_filter,
    )

    logger.debug(
        "query_parsed",
        jurisdiction=jurisdiction,
        case_type=case_type,
        citations=citations,
        query_type=query_type,
        bm25_weight=bm25_weight,
    )
    return parsed


def _classify_query(query: str) -> tuple[str, float, float]:
    """
    Classify query and return (query_type, bm25_weight, authority_alpha).

    Citation lookups:
        BM25 weight=0.70 — exact keyword match matters most.
        Authority alpha=0.35 — court level matters for citation questions.

    Semantic queries:
        BM25 weight=0.30 — conceptual similarity is primary.
        Authority alpha=0.25 — relevance matters more than court level.

    Hybrid (default):
        BM25 weight=0.50
        Authority alpha=0.30
    """
    has_citation = bool(_CITATION_LOOKUP_SIGNALS.search(query))
    has_semantic = bool(_SEMANTIC_SIGNALS.search(query))

    if has_citation and not has_semantic:
        return "citation_lookup", 0.70, 0.35
    if has_semantic and not has_citation:
        return "semantic", 0.30, 0.25
    return "hybrid", 0.50, 0.30


def _needs_temporal_filter(lower: str) -> bool:
    """Heuristic: does the query imply interest in *current* law?"""
    current_signals = {
        "current", "current law", "currently", "now", "today",
        "still valid", "still in effect", "still applies",
        "effective", "in force",
    }
    return any(sig in lower for sig in current_signals)


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
