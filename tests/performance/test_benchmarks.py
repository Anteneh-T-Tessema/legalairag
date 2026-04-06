"""Performance benchmarks for IndyLeg core paths.

Run:
    pytest tests/performance/ -v --timeout=120

These tests measure wall-clock time of key code paths (with external I/O
mocked) and assert that they complete within acceptable budgets. They are
intentionally conservative — the goal is to catch regressions, not enforce
micro-benchmarks.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from retrieval.hybrid_search import SearchResult
from retrieval.query_parser import parse_legal_query

# ── Shared fixtures ──────────────────────────────────────────────────────────

_MANY_RESULTS = [
    SearchResult(
        chunk_id=f"chunk-{i:04d}",
        source_id=f"src-{i:04d}",
        content=f"Document chunk {i} — Indiana Code placeholder text for benchmark.",
        section=f"§ {i}",
        citations=[f"35-42-1-{i}"],
        metadata={"court": "ind"},
        score=0.90 - (i * 0.005),
    )
    for i in range(200)
]


# ── Query parsing throughput ─────────────────────────────────────────────────


class TestQueryParserPerformance:
    """parse_legal_query is pure Python — should be <1 ms per call."""

    def test_throughput_1000_queries(self):
        queries = [
            "What is the eviction notice requirement in Marion County?",
            "IC § 35-42-1-1 murder statute",
            "child custody modification Hamilton County",
            "statute of limitations personal injury Indiana",
            "small claims filing fee Lake County 2024",
        ]
        start = time.perf_counter()
        for _ in range(200):
            for q in queries:
                parse_legal_query(q)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"1000 query parses took {elapsed:.2f}s (budget: 5s)"

    def test_complex_citation_query(self):
        """A query with many citations should still parse quickly."""
        q = "Compare IC § 35-42-1-1, IC § 35-42-1-2, IC § 35-44-1-3, IC § 32-31-1-6"
        start = time.perf_counter()
        for _ in range(500):
            parse_legal_query(q)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"500 citation parses took {elapsed:.2f}s (budget: 3s)"


# ── Reranker throughput ──────────────────────────────────────────────────────


class TestRerankerPerformance:
    """Reranker with mocked model should handle 200 results in < 2s."""

    @pytest.mark.asyncio
    async def test_rerank_200_results(self):
        from retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()

        # Mock the cross-encoder model to return dummy scores
        import numpy as np

        reranker._model = MagicMock()
        reranker._model.predict = MagicMock(
            return_value=np.array([0.9 - (i * 0.004) for i in range(200)])
        )

        start = time.perf_counter()
        result = await reranker.rerank(query="murder statute Indiana", results=_MANY_RESULTS)
        elapsed = time.perf_counter() - start

        assert len(result) > 0
        assert elapsed < 2.0, f"Reranking 200 results took {elapsed:.2f}s (budget: 2s)"


# ── Authority ranking throughput ─────────────────────────────────────────────


class TestAuthorityPerformance:
    """Authority rerank is CPU-only (citation graph) — should be fast."""

    def test_authority_rerank_200_results(self):
        from retrieval.authority import AuthorityRanker

        ranker = AuthorityRanker()

        start = time.perf_counter()
        result = ranker.rerank(_MANY_RESULTS[:100])
        elapsed = time.perf_counter() - start

        assert len(result) > 0
        assert elapsed < 1.0, f"Authority rerank took {elapsed:.2f}s (budget: 1s)"


# ── Full agent pipeline latency (mocked I/O) ────────────────────────────────


class TestPipelineLatency:
    """End-to-end agent.run() with all I/O mocked — measures orchestration overhead."""

    @pytest.mark.asyncio
    async def test_research_agent_orchestration_overhead(self):
        from agents.research_agent import CaseResearchAgent
        from generation.generator import GenerationResult
        from generation.validator import ValidationResult

        with (
            patch("agents.research_agent.BedrockEmbedder"),
            patch("agents.research_agent.HybridSearcher"),
            patch("agents.research_agent.CrossEncoderReranker"),
            patch("agents.research_agent.AuthorityRanker"),
            patch("agents.research_agent.LegalGenerator"),
        ):
            agent = CaseResearchAgent()

        agent._embedder.embed_query = AsyncMock(return_value=[0.1] * 1536)
        agent._searcher.search = AsyncMock(return_value=_MANY_RESULTS[:20])
        agent._reranker.rerank = AsyncMock(return_value=_MANY_RESULTS[:5])
        agent._authority.rerank = MagicMock(return_value=_MANY_RESULTS[:5])
        agent._generator.generate = AsyncMock(
            return_value=GenerationResult(
                answer="Test answer grounded in sources.",
                source_ids=["src-0000"],
                validation=ValidationResult(
                    is_valid=True,
                    cited_source_ids=["src-0000"],
                    uncited_claims=[],
                    missing_citations=[],
                ),
                model_id="test",
            )
        )

        # Warm up
        await agent.run(query="warm up query")

        # Benchmark 50 runs
        start = time.perf_counter()
        for _ in range(50):
            await agent.run(query="What is felony murder in Indiana?")
        elapsed = time.perf_counter() - start

        per_call = elapsed / 50
        assert per_call < 0.05, f"Agent orchestration: {per_call * 1000:.1f}ms/call (budget: 50ms)"


# ── Concurrent API request simulation ────────────────────────────────────────


class TestConcurrentRequests:
    """Simulate concurrent search requests to test for contention."""

    @pytest.mark.asyncio
    async def test_concurrent_query_parsing(self):
        import asyncio

        queries = [f"eviction notice county-{i} Indiana IC § 35-42-1-{i}" for i in range(100)]

        async def parse_one(q: str) -> Any:
            return parse_legal_query(q)

        start = time.perf_counter()
        results = await asyncio.gather(*(parse_one(q) for q in queries))
        elapsed = time.perf_counter() - start

        assert len(results) == 100
        assert elapsed < 2.0, f"100 concurrent parses took {elapsed:.2f}s (budget: 2s)"
