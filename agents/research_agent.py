from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.base_agent import BaseAgent
from generation.generator import GenerationResult, LegalGenerator
from ingestion.pipeline.embedder import BedrockEmbedder
from retrieval.hybrid_search import HybridSearcher
from retrieval.query_parser import parse_legal_query
from retrieval.reranker import CrossEncoderReranker


@dataclass
class ResearchResult:
    query: str
    answer: str
    source_ids: list[str]
    jurisdiction: str | None
    confidence: str        # "High" | "Medium" | "Low"
    citations: list[str]
    run_id: str


class CaseResearchAgent(BaseAgent):
    """
    Multi-step legal case research agent.

    Steps:
    1. Parse query (detect jurisdiction, case type, citations)
    2. Embed query → Bedrock Titan
    3. Hybrid search (vector + BM25 + RRF)
    4. Cross-encoder re-ranking
    5. Citation-grounded generation
    6. Confidence estimation based on retrieval score distribution

    Tool access: query_parse, embed, search, rerank, generate
    """

    allowed_tools = ["query_parse", "embed", "search", "rerank", "generate"]

    def __init__(self) -> None:
        super().__init__()
        self._embedder = BedrockEmbedder()
        self._searcher = HybridSearcher()
        self._reranker = CrossEncoderReranker()
        self._generator = LegalGenerator()

    async def _execute(self, **kwargs: Any) -> ResearchResult:
        query: str = kwargs["query"]

        # Step 1: Parse
        self._record_tool_call("query_parse", {"query": query})
        parsed = parse_legal_query(query)

        # Step 2: Embed
        self._record_tool_call("embed", {"query": parsed.normalized})
        query_vector = await self._embedder.embed_query(parsed.normalized)

        # Step 3: Hybrid search
        self._record_tool_call(
            "search",
            {
                "jurisdiction": parsed.jurisdiction,
                "case_type": parsed.case_type,
            },
        )
        candidates = await self._searcher.search(
            query_vector=query_vector,
            query_text=parsed.normalized,
            jurisdiction=parsed.jurisdiction,
            case_type=parsed.case_type,
        )

        # Step 4: Re-rank
        self._record_tool_call("rerank", {"candidate_count": len(candidates)})
        ranked = await self._reranker.rerank(query=parsed.normalized, results=candidates)

        # Step 5: Generate
        self._record_tool_call("generate", {"context_count": len(ranked)})
        result: GenerationResult = await self._generator.generate(
            query=query,
            context_chunks=ranked,
            jurisdiction=parsed.jurisdiction,
        )

        confidence = _estimate_confidence(ranked)

        all_citations = list(
            {c for chunk in ranked for c in chunk.citations}
        )

        return ResearchResult(
            query=query,
            answer=result.answer,
            source_ids=result.source_ids,
            jurisdiction=parsed.jurisdiction,
            confidence=confidence,
            citations=all_citations,
            run_id=self._run_id,
        )


def _estimate_confidence(ranked_results: list) -> str:
    """
    Confidence heuristic based on top result RRF score.
    Thresholds are tunable as the system accumulates real query data.
    """
    if not ranked_results:
        return "Low"
    top_score = ranked_results[0].score
    if top_score > 0.02:
        return "High"
    if top_score > 0.01:
        return "Medium"
    return "Low"
