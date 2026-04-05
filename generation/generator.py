from __future__ import annotations

import asyncio
from dataclasses import dataclass

from config.logging import get_logger
from generation.bedrock_client import BedrockLLMClient
from generation.prompts.legal_qa import (
    build_legal_qa_system_prompt,
    build_legal_qa_user_prompt,
)
from generation.validator import ValidationResult, validate_generated_output
from retrieval.hybrid_search import SearchResult

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    answer: str
    source_ids: list[str]
    validation: ValidationResult
    model_id: str


_FALLBACK = (
    "The provided documents do not contain sufficient information to answer this question. "
    "Please consult a qualified Indiana attorney or review the Indiana Code directly at "
    "https://iga.in.gov/laws/indiana-code."
)


class LegalGenerator:
    """
    Citation-grounded legal answer generation using AWS Bedrock (Claude).

    Design:
    - System prompt enforces citation discipline.
    - Post-generation validation checks all [SOURCE:] markers against context.
    - If validation fails (hallucinated citations), the answer is replaced with a fallback
      rather than exposing a potentially false result to legal staff.
    - temperature=0.0 for determinism and auditability.
    """

    def __init__(self) -> None:
        self._client = BedrockLLMClient()

    async def generate(
        self,
        query: str,
        context_chunks: list[SearchResult],
        jurisdiction: str | None = None,
    ) -> GenerationResult:
        if not context_chunks:
            logger.warning("empty_context", query=query[:80])
            return GenerationResult(
                answer=_FALLBACK,
                source_ids=[],
                validation=ValidationResult(
                    is_valid=True,
                    cited_source_ids=[],
                    uncited_claims=[],
                    missing_citations=[],
                    warnings=["empty_context"],
                ),
                model_id=self._client._model_id,
            )

        system = build_legal_qa_system_prompt(jurisdiction)
        user = build_legal_qa_user_prompt(query, context_chunks)

        # Run LLM call in executor (synchronous boto3)
        loop = asyncio.get_event_loop()
        raw_answer = await loop.run_in_executor(
            None,
            lambda: self._client.complete(
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=0.0,
            ),
        )

        validation = validate_generated_output(raw_answer, context_chunks)

        if not validation.is_valid:
            logger.error(
                "citation_hallucination",
                missing=validation.missing_citations,
                query=query[:80],
            )
            answer = _FALLBACK
        else:
            answer = raw_answer

        return GenerationResult(
            answer=answer,
            source_ids=validation.cited_source_ids,
            validation=validation,
            model_id=self._client._model_id,
        )
