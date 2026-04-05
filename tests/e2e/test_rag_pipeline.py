"""End-to-end tests for the IndyLeg RAG pipeline.

All external I/O (Bedrock, pgvector, SQS) is mocked so the tests run offline.

What these tests exercise:
  - Full CaseResearchAgent.run() call path: parse → embed → search → rerank
    → authority-rank → generate → ResearchResult
  - FraudDetectionAgent.run() call path with synthetic filing data
  - parse_legal_query correctly feeds bm25_weight / query_type into the searcher

Run:
    pytest tests/e2e/ -v
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.research_agent import CaseResearchAgent, ResearchResult
from agents.fraud_detection_agent import FraudDetectionAgent, FraudAnalysisResult
from retrieval.hybrid_search import SearchResult
from retrieval.query_parser import parse_legal_query


# ── Shared test data ──────────────────────────────────────────────────────────

_SAMPLE_STATUTES = [
    SearchResult(
        chunk_id="chunk-001",
        source_id="ic-35-42-1-1",
        content=(
            "IC 35-42-1-1 Murder. A person who knowingly or intentionally kills another "
            "human being commits murder, a felony."
        ),
        section="§ 35-42-1-1",
        citations=["35-42-1-1"],
        metadata={"court": "ind", "jurisdiction": "indiana", "doc_type": "statute"},
        score=0.91,
    ),
    SearchResult(
        chunk_id="chunk-002",
        source_id="ic-35-42-1-2",
        content="IC 35-42-1-2 Voluntary manslaughter.",
        section="§ 35-42-1-2",
        citations=["35-42-1-2"],
        metadata={"court": "ind", "jurisdiction": "indiana", "doc_type": "statute"},
        score=0.78,
    ),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_generation_result(answer: str = "Test answer.") -> Any:
    from generation.generator import GenerationResult  # noqa: PLC0415
    from generation.validator import ValidationResult  # noqa: PLC0415
    return GenerationResult(
        answer=answer,
        source_ids=["ic-35-42-1-1"],
        validation=ValidationResult(
            is_valid=True,
            cited_source_ids=["ic-35-42-1-1"],
            uncited_claims=[],
            missing_citations=[],
        ),
        model_id="amazon.titan-text-express-v1",
    )


# ── parse_legal_query (pure — no mocks needed) ────────────────────────────────

def test_citation_query_sets_high_bm25_weight():
    # Pure citation — no semantic words like "what" or "how"
    parsed = parse_legal_query("Ind. Code § 35-42-1-1 murder statute text")
    assert parsed.query_type == "citation_lookup"
    assert parsed.bm25_weight > 0.5


def test_semantic_query_sets_low_bm25_weight():
    parsed = parse_legal_query("How does Indiana define felony murder?")
    assert parsed.query_type == "semantic"
    assert parsed.bm25_weight < 0.5


def test_jurisdiction_extracted():
    parsed = parse_legal_query("What are the small claims limits in Marion county?")
    assert parsed.jurisdiction is not None
    assert "Marion" in parsed.jurisdiction


def test_case_type_extracted():
    parsed = parse_legal_query("What happens in a felony case?")
    assert parsed.case_type == "Criminal"


def test_citations_extracted():
    parsed = parse_legal_query("Explain IC § 35-42-1-1 and I.C. § 35-44-1-3.")
    assert len(parsed.citations_mentioned) >= 1


def test_current_law_enables_temporal_filter():
    parsed = parse_legal_query("What is the current law on bail in Indiana?")
    assert parsed.temporal_filter is True


# ── CaseResearchAgent end-to-end ──────────────────────────────────────────────

@pytest.fixture()
def mock_agent() -> CaseResearchAgent:
    """
    Build a CaseResearchAgent with all external collaborators mocked.
    Avoids boto3 / psycopg calls entirely.
    """
    with (
        patch("agents.research_agent.BedrockEmbedder"),
        patch("agents.research_agent.HybridSearcher"),
        patch("agents.research_agent.CrossEncoderReranker"),
        patch("agents.research_agent.AuthorityRanker"),
        patch("agents.research_agent.LegalGenerator"),
    ):
        agent = CaseResearchAgent()

    # Configure mock collaborators
    agent._embedder.embed_query = AsyncMock(return_value=[0.1] * 1536)
    agent._searcher.search = AsyncMock(return_value=list(_SAMPLE_STATUTES))
    agent._reranker.rerank = AsyncMock(return_value=list(_SAMPLE_STATUTES))
    agent._authority.rank = MagicMock(return_value=list(_SAMPLE_STATUTES))
    agent._generator.generate = AsyncMock(
        return_value=_make_generation_result("Under IC § 35-42-1-1, murder is a felony.")
    )
    return agent


@pytest.mark.asyncio
async def test_research_agent_returns_result(mock_agent: CaseResearchAgent):
    result = await mock_agent.run(query="What is the Indiana murder statute?")
    assert isinstance(result, ResearchResult)
    assert result.answer
    assert result.run_id


@pytest.mark.asyncio
async def test_research_agent_answer_not_empty(mock_agent: CaseResearchAgent):
    result = await mock_agent.run(query="Explain IC 35-42-1-1")
    assert len(result.answer) > 0


@pytest.mark.asyncio
async def test_research_agent_source_ids_populated(mock_agent: CaseResearchAgent):
    result = await mock_agent.run(query="What does Indiana say about felony murder?")
    assert len(result.source_ids) > 0


@pytest.mark.asyncio
async def test_research_agent_confidence_valid(mock_agent: CaseResearchAgent):
    result = await mock_agent.run(query="Define voluntary manslaughter in Indiana")
    assert result.confidence in {"High", "Medium", "Low"}


@pytest.mark.asyncio
async def test_research_agent_calls_embedder(mock_agent: CaseResearchAgent):
    await mock_agent.run(query="Search for murder statutes")
    mock_agent._embedder.embed_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_agent_calls_searcher(mock_agent: CaseResearchAgent):
    await mock_agent.run(query="IC § 35-42-1-1")
    mock_agent._searcher.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_agent_search_uses_bm25_weight(mock_agent: CaseResearchAgent):
    """Citation-lookup queries should pass a higher bm25_weight to the searcher."""
    await mock_agent.run(query="Find Ind. Code § 35-42-1-1 text")
    call_kwargs = mock_agent._searcher.search.call_args.kwargs
    assert "bm25_weight" in call_kwargs
    assert call_kwargs["bm25_weight"] > 0.5


@pytest.mark.asyncio
async def test_research_agent_calls_reranker(mock_agent: CaseResearchAgent):
    await mock_agent.run(query="murder statute Indiana")
    mock_agent._reranker.rerank.assert_awaited_once()


@pytest.mark.asyncio
async def test_research_agent_empty_search_returns_low_confidence(
    mock_agent: CaseResearchAgent,
):
    """Zero search results → confidence should be Low."""
    mock_agent._searcher.search = AsyncMock(return_value=[])
    mock_agent._reranker.rerank = AsyncMock(return_value=[])
    # Modify return_value rather than replacing the mock (avoids reference aliasing)
    mock_agent._authority.rank.return_value = []
    mock_agent._generator.generate = AsyncMock(
        return_value=_make_generation_result("No relevant documents found.")
    )
    result = await mock_agent.run(query="Something very obscure not in the corpus")
    assert result.confidence == "Low"


# ── FraudDetectionAgent end-to-end ────────────────────────────────────────────

def _fraud_search_results() -> list[SearchResult]:
    """Synthetic results with burst filing + deed fraud patterns."""
    from datetime import date, timedelta  # noqa: PLC0415

    results = []
    for i in range(8):
        d = date(2024, 6, 1) + timedelta(days=i)
        results.append(SearchResult(
            chunk_id=f"fraud-{i}",
            source_id=f"fraud-src-{i}",
            content="Property transfer case filing.",
            section="",
            citations=[],
            metadata={
                "parties": ["Shell Co LLC"],
                "filing_date": d.isoformat(),
            },
            score=0.7,
        ))
    for i in range(3):
        results.append(SearchResult(
            chunk_id=f"deed-{i}",
            source_id=f"deed-src-{i}",
            content="This quitclaim deed transfers property for the sum of $1.00.",
            section="",
            citations=[],
            metadata={},
            score=0.6,
        ))
    return results


@pytest.fixture()
def mock_fraud_agent() -> FraudDetectionAgent:
    with (
        patch("agents.fraud_detection_agent.BedrockEmbedder"),
        patch("agents.fraud_detection_agent.HybridSearcher"),
    ):
        agent = FraudDetectionAgent()

    agent._embedder.embed_query = AsyncMock(return_value=[0.1] * 1536)
    agent._searcher.search = AsyncMock(return_value=_fraud_search_results())
    return agent


@pytest.mark.asyncio
async def test_fraud_agent_returns_result(mock_fraud_agent: FraudDetectionAgent):
    result = await mock_fraud_agent.run(
        query="Shell Co LLC property transfers in Indianapolis 2024"
    )
    assert isinstance(result, FraudAnalysisResult)


@pytest.mark.asyncio
async def test_fraud_agent_detects_burst_filing(mock_fraud_agent: FraudDetectionAgent):
    result = await mock_fraud_agent.run(query="Shell Co burst filings")
    types = {ind.indicator_type for ind in result.indicators}
    assert "burst_filing" in types


@pytest.mark.asyncio
async def test_fraud_agent_detects_deed_fraud(mock_fraud_agent: FraudDetectionAgent):
    result = await mock_fraud_agent.run(query="Quitclaim deed nominal transfers")
    types = {ind.indicator_type for ind in result.indicators}
    assert "deed_fraud_pattern" in types


@pytest.mark.asyncio
async def test_fraud_agent_risk_level_not_none(mock_fraud_agent: FraudDetectionAgent):
    result = await mock_fraud_agent.run(query="fraud analysis")
    assert result.risk_level in {"none", "low", "medium", "high", "critical"}


@pytest.mark.asyncio
async def test_fraud_agent_requires_review_when_high_risk(
    mock_fraud_agent: FraudDetectionAgent,
):
    result = await mock_fraud_agent.run(query="Shell Co burst + deed fraud")
    if result.risk_level in {"high", "critical"}:
        assert result.requires_human_review is True


@pytest.mark.asyncio
async def test_fraud_agent_run_id_unique():
    with (
        patch("agents.fraud_detection_agent.BedrockEmbedder"),
        patch("agents.fraud_detection_agent.HybridSearcher"),
    ):
        agent1 = FraudDetectionAgent()
        agent2 = FraudDetectionAgent()

    agent1._embedder.embed_query = AsyncMock(return_value=[0.1] * 1536)
    agent1._searcher.search = AsyncMock(return_value=[])
    agent2._embedder.embed_query = AsyncMock(return_value=[0.1] * 1536)
    agent2._searcher.search = AsyncMock(return_value=[])

    r1 = await agent1.run(query="test q1")
    r2 = await agent2.run(query="test q2")
    assert r1.run_id != r2.run_id
