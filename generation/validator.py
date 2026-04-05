from __future__ import annotations

import re
from dataclasses import dataclass, field

from config.logging import get_logger
from retrieval.hybrid_search import SearchResult

logger = get_logger(__name__)

# Match [SOURCE: xxx] citation markers in generated text
_SOURCE_CITE_RE = re.compile(r"\[SOURCE:\s*([^\],]+?)(?:,\s*§[^\]]+)?\]")


@dataclass
class ValidationResult:
    is_valid: bool
    cited_source_ids: list[str]
    uncited_claims: list[str]
    missing_citations: list[str]  # cited in output but not in context
    warnings: list[str] = field(default_factory=list)


def validate_generated_output(
    generated_text: str,
    context_chunks: list[SearchResult],
) -> ValidationResult:
    """
    Post-generation validation:
    1. Check that every [SOURCE: id] in the output maps to a real context chunk.
    2. Detect uncited assertions (sentences that make factual claims without a citation).
    3. Flag if the model deflected (fallback response detected).

    This is a critical compliance feature for government legal systems —
    all outputs must be traceable back to source documents.
    """
    known_ids = {chunk.source_id for chunk in context_chunks}
    cited_ids = _SOURCE_CITE_RE.findall(generated_text)
    cited_ids_cleaned = [cid.strip() for cid in cited_ids]

    missing = [cid for cid in cited_ids_cleaned if cid not in known_ids]
    uncited = _find_uncited_claims(generated_text)

    warnings: list[str] = []
    if "do not contain sufficient information" in generated_text.lower():
        warnings.append("fallback_response_detected")
    if not cited_ids_cleaned:
        warnings.append("no_citations_in_output")

    is_valid = len(missing) == 0

    if missing:
        logger.warning(
            "hallucinated_citations",
            missing_source_ids=missing,
            text_preview=generated_text[:200],
        )

    return ValidationResult(
        is_valid=is_valid,
        cited_source_ids=cited_ids_cleaned,
        uncited_claims=uncited,
        missing_citations=missing,
        warnings=warnings,
    )


def _find_uncited_claims(text: str) -> list[str]:
    """
    Heuristic: find sentences that contain definitive legal assertions
    (e.g. "the statute requires", "the court held") without a citation marker.
    Not exhaustive — intended as a QA signal, not a blocker.
    """
    assertion_patterns = re.compile(
        r"\b(?:requires?|states?|provides?|mandates?|prohibits?|held|ruled|decided)\b",
        re.IGNORECASE,
    )
    sentences = re.split(r"(?<=[.!?])\s+", text)
    uncited: list[str] = []
    for sent in sentences:
        if assertion_patterns.search(sent) and "[SOURCE:" not in sent:
            uncited.append(sent.strip())
    return uncited
