from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from generation.generator import GenerationResult, LegalGenerator, _FALLBACK
from generation.validator import ValidationResult, validate_generated_output
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


# ── LegalGenerator (full generate() pipeline) ────────────────────────────────

def _make_context_chunks(source_ids: list[str]) -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id=f"chunk-{sid}",
            source_id=sid,
            content=f"The statute provides relevant content for {sid}.",
            section="SECTION 1",
            citations=["Ind. Code § 35-42-1-1"],
            metadata={},
            score=0.9,
        )
        for sid in source_ids
    ]


class TestLegalGenerator:
    def _make_generator(self) -> LegalGenerator:
        gen = LegalGenerator.__new__(LegalGenerator)
        gen._client = MagicMock()
        gen._client._model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
        return gen

    @pytest.mark.asyncio
    async def test_empty_context_returns_fallback_without_bedrock_call(self) -> None:
        gen = self._make_generator()
        result = await gen.generate("What is the penalty?", [])
        assert result.answer == _FALLBACK
        assert result.source_ids == []
        assert "empty_context" in result.validation.warnings
        gen._client.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_context_result_is_generation_result(self) -> None:
        gen = self._make_generator()
        result = await gen.generate("query", [])
        assert isinstance(result, GenerationResult)

    @pytest.mark.asyncio
    async def test_valid_context_returns_raw_answer(self) -> None:
        gen = self._make_generator()
        chunks = _make_context_chunks(["case-001"])
        raw = "The penalty is severe [SOURCE: case-001]."
        gen._client.complete = MagicMock(return_value=raw)

        valid_result = ValidationResult(
            is_valid=True,
            cited_source_ids=["case-001"],
            uncited_claims=[],
            missing_citations=[],
            warnings=[],
        )
        with patch("generation.generator.validate_generated_output", return_value=valid_result):
            result = await gen.generate("What is the penalty?", chunks)

        assert result.answer == raw
        assert result.source_ids == ["case-001"]
        assert result.validation.is_valid is True

    @pytest.mark.asyncio
    async def test_hallucinated_citations_return_fallback(self) -> None:
        gen = self._make_generator()
        chunks = _make_context_chunks(["case-001"])
        gen._client.complete = MagicMock(return_value="See [SOURCE: case-999] for details.")

        invalid_result = ValidationResult(
            is_valid=False,
            cited_source_ids=[],
            uncited_claims=[],
            missing_citations=["case-999"],
            warnings=[],
        )
        with patch("generation.generator.validate_generated_output", return_value=invalid_result):
            result = await gen.generate("What?", chunks)

        assert result.answer == _FALLBACK
        assert result.validation.is_valid is False
        assert "case-999" in result.validation.missing_citations

    @pytest.mark.asyncio
    async def test_jurisdiction_forwarded_to_system_prompt(self) -> None:
        gen = self._make_generator()
        chunks = _make_context_chunks(["case-001"])
        gen._client.complete = MagicMock(return_value="Answer [SOURCE: case-001].")

        valid_result = ValidationResult(
            is_valid=True,
            cited_source_ids=["case-001"],
            uncited_claims=[],
            missing_citations=[],
            warnings=[],
        )
        with (
            patch("generation.generator.build_legal_qa_system_prompt") as mock_sys,
            patch("generation.generator.build_legal_qa_user_prompt", return_value="user prompt"),
            patch("generation.generator.validate_generated_output", return_value=valid_result),
        ):
            mock_sys.return_value = "System prompt"
            await gen.generate("query", chunks, jurisdiction="Indiana")

        mock_sys.assert_called_once_with("Indiana")

    @pytest.mark.asyncio
    async def test_model_id_propagated_to_result(self) -> None:
        gen = self._make_generator()
        chunks = _make_context_chunks(["case-001"])
        gen._client.complete = MagicMock(return_value="Answer [SOURCE: case-001].")

        valid_result = ValidationResult(
            is_valid=True,
            cited_source_ids=["case-001"],
            uncited_claims=[],
            missing_citations=[],
            warnings=[],
        )
        with patch("generation.generator.validate_generated_output", return_value=valid_result):
            result = await gen.generate("query", chunks)

        assert result.model_id == "anthropic.claude-3-sonnet-20240229-v1:0"

    @pytest.mark.asyncio
    async def test_bedrock_client_called_with_correct_messages(self) -> None:
        gen = self._make_generator()
        chunks = _make_context_chunks(["case-001"])
        gen._client.complete = MagicMock(return_value="Answer [SOURCE: case-001].")

        valid_result = ValidationResult(
            is_valid=True,
            cited_source_ids=["case-001"],
            uncited_claims=[],
            missing_citations=[],
            warnings=[],
        )
        with patch("generation.generator.validate_generated_output", return_value=valid_result):
            await gen.generate("What is the penalty?", chunks)

        gen._client.complete.assert_called_once()
        call_kwargs = gen._client.complete.call_args.kwargs
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["messages"][0]["role"] == "user"
