from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agents.research_agent import CaseResearchAgent
from api.auth import UserInfo, get_current_user
from api.schemas.search import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from ingestion.pipeline.embedder import BedrockEmbedder
from retrieval.hybrid_search import HybridSearcher
from retrieval.query_parser import parse_legal_query
from retrieval.reranker import CrossEncoderReranker

router = APIRouter(prefix="/search", tags=["search"])

# Shared instances (one per process; thread-safe for read-only operations)
_embedder = BedrockEmbedder()
_searcher = HybridSearcher()
_reranker = CrossEncoderReranker()
_agent = CaseResearchAgent()


@router.post("", response_model=SearchResponse)
async def search(req: SearchRequest, _user: UserInfo = Depends(get_current_user)) -> SearchResponse:
    """
    Hybrid vector + BM25 search with cross-encoder re-ranking.
    Returns ranked chunks with citation metadata — no generation.
    Useful for power users who want raw retrieval results.
    """
    parsed = parse_legal_query(req.query)
    query_vector = await _embedder.embed_query(parsed.normalized)

    candidates = await _searcher.search(
        query_vector=query_vector,
        query_text=parsed.normalized,
        jurisdiction=req.jurisdiction or parsed.jurisdiction,
        case_type=req.case_type or parsed.case_type,
        top_k=req.top_k * 4,  # over-fetch for re-ranker
        bm25_weight=parsed.bm25_weight,
    )

    ranked = await _reranker.rerank(
        query=parsed.normalized,
        results=candidates,
        top_k=req.top_k,
    )

    items = [
        SearchResultItem(
            chunk_id=r.chunk_id,
            source_id=r.source_id,
            section=r.section,
            content=r.content[:600],  # truncate for response size
            citations=r.citations,
            score=round(r.score, 6),
        )
        for r in ranked
    ]

    return SearchResponse(
        query=req.query,
        results=items,
        jurisdiction=req.jurisdiction or parsed.jurisdiction,
        total=len(items),
    )


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, _user: UserInfo = Depends(get_current_user)) -> AskResponse:
    """
    Full RAG pipeline: retrieve → re-rank → generate citation-grounded answer.
    Uses the CaseResearchAgent for multi-step reasoning with audit trail.
    """
    try:
        result = await _agent.run(query=req.query)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research agent failed: {exc}",
        ) from exc

    return AskResponse(
        query=req.query,
        answer=result.answer,
        source_ids=result.source_ids,
        citations=result.citations,
        confidence=result.confidence,
        run_id=result.run_id,
        validation_passed=True,
    )
