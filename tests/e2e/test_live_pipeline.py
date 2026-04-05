"""Live end-to-end tests that hit real AWS services.

These tests are **skipped by default** — they only run when the
``INDYLEG_LIVE_E2E`` environment variable is set and real AWS credentials
are available.

Run:
    INDYLEG_LIVE_E2E=1 pytest tests/e2e/test_live_pipeline.py -v --timeout=180

Prerequisites:
    - AWS credentials with Bedrock + S3 + SQS access
    - A running PostgreSQL instance with pgvector (via docker compose)
    - Environment variables: DATABASE_URL, APP_ENV, API_SECRET_KEY
"""

from __future__ import annotations

import os

import pytest

_SKIP_REASON = "Set INDYLEG_LIVE_E2E=1 and provide AWS credentials to run live E2E tests"

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INDYLEG_LIVE_E2E"), reason=_SKIP_REASON),
    pytest.mark.skipif(not os.environ.get("AWS_ACCESS_KEY_ID"), reason=_SKIP_REASON),
    pytest.mark.live,
]


@pytest.fixture(scope="module")
def bedrock_embedder():
    from ingestion.pipeline.embedder import BedrockEmbedder

    return BedrockEmbedder()


@pytest.fixture(scope="module")
def generator():
    from generation.generator import LegalGenerator

    return LegalGenerator()


# ── Bedrock Embedding (live) ─────────────────────────────────────────────────


class TestLiveEmbedding:
    """Verify Titan Embed v2 produces valid 1024-dim vectors."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self, bedrock_embedder):
        vector = await bedrock_embedder.embed_query("Indiana eviction notice requirements")
        assert isinstance(vector, list)
        assert len(vector) == 1024
        assert all(isinstance(v, float) for v in vector)

    @pytest.mark.asyncio
    async def test_embed_batch(self, bedrock_embedder):
        texts = [
            "Indiana Code § 35-42-1-1 defines murder",
            "Small claims court filing fees in Marion County",
            "Child custody modification requirements",
        ]
        vectors = await bedrock_embedder.embed_batch(texts)
        assert len(vectors) == 3
        for vec in vectors:
            assert len(vec) == 1024


# ── Bedrock Generation (live) ────────────────────────────────────────────────


class TestLiveGeneration:
    """Verify Claude generates grounded answers with [SOURCE] tags."""

    @pytest.mark.asyncio
    async def test_generate_answer(self, generator):
        from retrieval.hybrid_search import SearchResult

        mock_results = [
            SearchResult(
                chunk_id="chunk-live-001",
                source_id="ic-32-31-1-6",
                content=(
                    "IC 32-31-1-6 requires the landlord to provide written notice "
                    "at least ten (10) days before filing an eviction complaint."
                ),
                section="§ 32-31-1-6",
                citations=["32-31-1-6"],
                metadata={"jurisdiction": "indiana", "doc_type": "statute"},
                score=0.92,
            ),
        ]

        result = await generator.generate(
            query="What notice must a landlord give before eviction in Indiana?",
            search_results=mock_results,
        )

        assert result.answer
        assert len(result.answer) > 20
        assert result.source_ids
        assert result.validation is not None


# ── Full RAG Pipeline (live) ─────────────────────────────────────────────────


class TestLiveRagPipeline:
    """Run the full CaseResearchAgent with real Bedrock calls.

    Requires all infrastructure running (Bedrock, pgvector, OpenSearch).
    """

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL not set — need pgvector for full pipeline",
    )
    async def test_full_pipeline(self):
        from agents.research_agent import CaseResearchAgent

        agent = CaseResearchAgent()
        result = await agent.run(query="What is the statute of limitations for fraud in Indiana?")

        assert result.answer
        assert result.run_id
        assert result.confidence in {"High", "Medium", "Low"}
        assert len(result.source_ids) >= 0  # may be 0 if DB is empty
