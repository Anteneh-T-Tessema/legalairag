"""Unit tests for agents.research_agent — CaseResearchAgent + _estimate_confidence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from agents.research_agent import CaseResearchAgent, ResearchResult, _estimate_confidence


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Helpers ───────────────────────────────────────────────────────────────────


@dataclass
class _FakeResult:
    score: float
    chunk_id: str = "c1"
    source_id: str = "src-1"
    content: str = "text"
    section: str = "§1"
    citations: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.citations is None:
            self.citations = ["Ind. Code § 1-2-3"]
        if self.metadata is None:
            self.metadata = {}


@dataclass
class _FakeParsed:
    normalized: str = "query text"
    jurisdiction: str | None = "Marion County"
    case_type: str | None = "Civil"
    query_type: str = "semantic"
    bm25_weight: float = 0.5
    temporal_filter: bool = False
    authority_alpha: float = 0.3
    keywords: list[str] | None = None


@dataclass
class _FakeGenResult:
    answer: str = "The answer is X."
    source_ids: list[str] | None = None

    def __post_init__(self):
        if self.source_ids is None:
            self.source_ids = ["src-1"]


# ── _estimate_confidence ──────────────────────────────────────────────────────


class TestEstimateConfidence:
    def test_empty_returns_low(self):
        assert _estimate_confidence([]) == "Low"

    def test_high_scores_with_gap_returns_high(self):
        results = [_FakeResult(score=0.025), _FakeResult(score=0.010)]
        assert _estimate_confidence(results) == "High"

    def test_single_result_low_score_returns_low(self):
        results = [_FakeResult(score=0.005)]
        assert _estimate_confidence(results) == "Low"

    def test_high_gap_returns_high(self):
        results = [_FakeResult(score=0.020), _FakeResult(score=0.010), _FakeResult(score=0.008)]
        assert _estimate_confidence(results) == "High"

    def test_medium_gap_returns_medium(self):
        results = [_FakeResult(score=0.012), _FakeResult(score=0.009), _FakeResult(score=0.008)]
        assert _estimate_confidence(results) == "Medium"

    def test_flat_distribution_returns_low(self):
        results = [_FakeResult(score=0.006), _FakeResult(score=0.005), _FakeResult(score=0.005)]
        assert _estimate_confidence(results) == "Low"


# ── CaseResearchAgent._execute ────────────────────────────────────────────


class TestCaseResearchAgent:
    def _build_mocks(self):
        candidates = [_FakeResult(score=0.020), _FakeResult(score=0.010)]

        with (
            patch("agents.research_agent.BedrockEmbedder") as MockEmbed,
            patch("agents.research_agent.HybridSearcher") as MockSearch,
            patch("agents.research_agent.CrossEncoderReranker") as MockRerank,
            patch("agents.research_agent.AuthorityRanker") as MockAuth,
            patch("agents.research_agent.LegalGenerator") as MockGen,
            patch("agents.research_agent.parse_legal_query") as mock_parse,
        ):
            MockEmbed.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)
            MockSearch.return_value.search = AsyncMock(return_value=candidates)
            MockRerank.return_value.rerank = AsyncMock(return_value=candidates)
            MockAuth.return_value.rerank = MagicMock(return_value=candidates)
            MockGen.return_value.generate = AsyncMock(return_value=_FakeGenResult())
            mock_parse.return_value = _FakeParsed()

            agent = CaseResearchAgent()
            return agent

    def test_execute_returns_research_result(self):
        candidates = [_FakeResult(score=0.020), _FakeResult(score=0.010)]

        with (
            patch("agents.research_agent.BedrockEmbedder") as MockEmbed,
            patch("agents.research_agent.HybridSearcher") as MockSearch,
            patch("agents.research_agent.CrossEncoderReranker") as MockRerank,
            patch("agents.research_agent.AuthorityRanker") as MockAuth,
            patch("agents.research_agent.LegalGenerator") as MockGen,
            patch("agents.research_agent.parse_legal_query") as mock_parse,
        ):
            MockEmbed.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)
            MockSearch.return_value.search = AsyncMock(return_value=candidates)
            MockRerank.return_value.rerank = AsyncMock(return_value=candidates)
            MockAuth.return_value.rerank = MagicMock(return_value=candidates)
            MockGen.return_value.generate = AsyncMock(return_value=_FakeGenResult())
            mock_parse.return_value = _FakeParsed()

            agent = CaseResearchAgent()
            result = _run(agent.run(query="What is self defense in Indiana?"))

            assert isinstance(result, ResearchResult)
            assert result.answer == "The answer is X."
            assert result.jurisdiction == "Marion County"
            assert result.confidence == "High"
            assert len(result.citations) > 0

    def test_execute_records_tool_calls(self):
        candidates = [_FakeResult(score=0.020)]

        with (
            patch("agents.research_agent.BedrockEmbedder") as MockEmbed,
            patch("agents.research_agent.HybridSearcher") as MockSearch,
            patch("agents.research_agent.CrossEncoderReranker") as MockRerank,
            patch("agents.research_agent.AuthorityRanker") as MockAuth,
            patch("agents.research_agent.LegalGenerator") as MockGen,
            patch("agents.research_agent.parse_legal_query") as mock_parse,
        ):
            MockEmbed.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)
            MockSearch.return_value.search = AsyncMock(return_value=candidates)
            MockRerank.return_value.rerank = AsyncMock(return_value=candidates)
            MockAuth.return_value.rerank = MagicMock(return_value=candidates)
            MockGen.return_value.generate = AsyncMock(return_value=_FakeGenResult())
            mock_parse.return_value = _FakeParsed()

            agent = CaseResearchAgent()
            _run(agent.run(query="test"))

            tool_names = [tc["tool"] for tc in agent._tool_log]
            assert "query_parse" in tool_names
            assert "embed" in tool_names
            assert "search" in tool_names
            assert "rerank" in tool_names
            assert "generate" in tool_names

    def test_execute_with_temporal_filter(self):
        candidates = [_FakeResult(score=0.020)]

        with (
            patch("agents.research_agent.BedrockEmbedder") as MockEmbed,
            patch("agents.research_agent.HybridSearcher") as MockSearch,
            patch("agents.research_agent.CrossEncoderReranker") as MockRerank,
            patch("agents.research_agent.AuthorityRanker") as MockAuth,
            patch("agents.research_agent.LegalGenerator") as MockGen,
            patch("agents.research_agent.parse_legal_query") as mock_parse,
            patch("agents.research_agent.filter_temporally_valid") as mock_filter,
        ):
            MockEmbed.return_value.embed_query = AsyncMock(return_value=[0.1] * 1024)
            MockSearch.return_value.search = AsyncMock(return_value=candidates)
            mock_filter.return_value = candidates
            MockRerank.return_value.rerank = AsyncMock(return_value=candidates)
            MockAuth.return_value.rerank = MagicMock(return_value=candidates)
            MockGen.return_value.generate = AsyncMock(return_value=_FakeGenResult())
            mock_parse.return_value = _FakeParsed(temporal_filter=True)

            agent = CaseResearchAgent()
            _run(agent.run(query="current Indiana eviction law"))

            mock_filter.assert_called_once_with(candidates)

    def test_allowed_tools(self):
        assert "query_parse" in CaseResearchAgent.allowed_tools
        assert "generate" in CaseResearchAgent.allowed_tools
        assert "delete" not in CaseResearchAgent.allowed_tools
