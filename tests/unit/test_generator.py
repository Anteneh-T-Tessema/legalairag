from __future__ import annotations

from generation.validator import validate_generated_output
from retrieval.hybrid_search import SearchResult


def _mock_chunks(source_ids: list[str]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id=f"chunk-{sid}",
            source_id=sid,
            content="The statute provides that...",
            section="SECTION 1",
            citations=["Ind. Code § 35-42-1-1"],
            metadata={},
            score=0.9,
        )
        for sid in source_ids
    ]


class TestValidator:
    def test_valid_output_passes(self) -> None:
        chunks = _mock_chunks(["case-001", "case-002"])
        text = "The statute requires intent [SOURCE: case-001, §1]. Under [SOURCE: case-002], ..."
        result = validate_generated_output(text, chunks)
        assert result.is_valid
        assert "case-001" in result.cited_source_ids
        assert "case-002" in result.cited_source_ids

    def test_hallucinated_source_fails_validation(self) -> None:
        chunks = _mock_chunks(["case-001"])
        text = "According to [SOURCE: case-999], the penalty is severe."
        result = validate_generated_output(text, chunks)
        assert not result.is_valid
        assert "case-999" in result.missing_citations

    def test_no_citations_generates_warning(self) -> None:
        chunks = _mock_chunks(["case-001"])
        text = "The statute provides no clear guidance here."
        result = validate_generated_output(text, chunks)
        assert "no_citations_in_output" in result.warnings

    def test_fallback_response_detected(self) -> None:
        chunks = _mock_chunks([])
        text = (
            "The provided documents do not contain sufficient information to answer this question."
        )
        result = validate_generated_output(text, chunks)
        assert "fallback_response_detected" in result.warnings

    def test_uncited_assertion_flagged(self) -> None:
        chunks = _mock_chunks(["case-001"])
        text = "The court held that the defendant was liable. [SOURCE: case-001] also states..."
        result = validate_generated_output(text, chunks)
        # First sentence has "held" but no [SOURCE:] — should be in uncited_claims
        assert any("held" in claim for claim in result.uncited_claims)
