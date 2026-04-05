"""Unit tests for generation.validator — citation validation & uncited claim detection."""

from __future__ import annotations

from generation.validator import _find_uncited_claims, validate_generated_output
from retrieval.hybrid_search import SearchResult


def _sr(source_id: str, content: str = "dummy") -> SearchResult:
    return SearchResult(
        chunk_id="c1",
        source_id=source_id,
        content=content,
        section="",
        citations=[],
        metadata={},
        score=0.9,
    )


# ── validate_generated_output ─────────────────────────────────────────────────


class TestValidateGeneratedOutput:
    def test_valid_with_matching_citation(self) -> None:
        text = "The statue requires X. [SOURCE: doc-1]"
        result = validate_generated_output(text, [_sr("doc-1")])
        assert result.is_valid is True
        assert result.cited_source_ids == ["doc-1"]
        assert result.missing_citations == []

    def test_invalid_with_hallucinated_citation(self) -> None:
        text = "Case law says Y. [SOURCE: phantom-999]"
        result = validate_generated_output(text, [_sr("doc-1")])
        assert result.is_valid is False
        assert "phantom-999" in result.missing_citations

    def test_no_citations_produces_warning(self) -> None:
        text = "This is a response with no citations."
        result = validate_generated_output(text, [_sr("doc-1")])
        assert "no_citations_in_output" in result.warnings

    def test_fallback_response_detected(self) -> None:
        text = "The sources do not contain sufficient information to answer."
        result = validate_generated_output(text, [_sr("doc-1")])
        assert "fallback_response_detected" in result.warnings

    def test_multiple_citations_mixed(self) -> None:
        text = (
            "Per [SOURCE: doc-1] and [SOURCE: doc-2], the rule applies. Also see [SOURCE: unknown]."
        )
        ctx = [_sr("doc-1"), _sr("doc-2")]
        result = validate_generated_output(text, ctx)
        assert result.is_valid is False
        assert set(result.cited_source_ids) == {"doc-1", "doc-2", "unknown"}
        assert result.missing_citations == ["unknown"]

    def test_empty_context_and_text(self) -> None:
        result = validate_generated_output("", [])
        assert result.is_valid is True
        assert result.cited_source_ids == []

    def test_citation_with_section(self) -> None:
        text = "See [SOURCE: doc-1, § 35-42-1-1] for details."
        result = validate_generated_output(text, [_sr("doc-1")])
        assert result.is_valid is True
        assert "doc-1" in result.cited_source_ids


# ── _find_uncited_claims ──────────────────────────────────────────────────────


class TestFindUncitedClaims:
    def test_detects_assertion_without_source(self) -> None:
        text = "The statute requires filing within 30 days."
        uncited = _find_uncited_claims(text)
        assert len(uncited) == 1
        assert "requires" in uncited[0].lower()

    def test_no_flag_when_citation_present(self) -> None:
        text = "The statute requires filing within 30 days [SOURCE: doc-1]."
        uncited = _find_uncited_claims(text)
        assert len(uncited) == 0

    def test_multiple_assertion_verbs(self) -> None:
        text = (
            "The court held that the defendant was guilty. The code provides for an appeal process."
        )
        uncited = _find_uncited_claims(text)
        assert len(uncited) == 2

    def test_no_assertions_returns_empty(self) -> None:
        text = "This is a general statement about law."
        assert _find_uncited_claims(text) == []
