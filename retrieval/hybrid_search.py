from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    chunk_id: str
    source_id: str
    content: str
    section: str
    citations: list[str]
    metadata: dict[str, Any]
    score: float = 0.0


class HybridSearcher:
    """
    Hybrid legal retrieval: dense vector search (pgvector) + sparse BM25,
    fused with Reciprocal Rank Fusion (RRF).

    Rationale:
    - Vector search → semantic relevance ("what does this mean?")
    - BM25           → precise citation / keyword retrieval ("find § 35-42-1-1")
    - RRF fusion    → combines both rank lists without score normalisation issues

    The BM25 index is built in-memory over retrieved vector candidates for
    efficiency; a full-corpus BM25 index lives in OpenSearch (see opensearch.py).
    """

    def __init__(
        self,
        database_url: str = settings.database_url,
        top_k: int = settings.retrieval_top_k,
        rrf_k: int = 60,
    ) -> None:
        self._database_url = database_url
        self._top_k = top_k
        self._rrf_k = rrf_k
        self._conn: Any = None

    async def search(
        self,
        query_vector: list[float],
        query_text: str,
        *,
        jurisdiction: str | None = None,
        case_type: str | None = None,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        k = top_k or self._top_k
        # Over-fetch candidates for RRF (typically 4× final k)
        candidate_n = min(k * 4, settings.rerank_top_k)

        dense_results = await self._vector_search(
            query_vector,
            n=candidate_n,
            jurisdiction=jurisdiction,
            case_type=case_type,
        )
        sparse_results = self._bm25_search(dense_results, query_text, n=candidate_n)
        fused = self._reciprocal_rank_fusion(dense_results, sparse_results, k=k)

        logger.info(
            "hybrid_search",
            dense_candidates=len(dense_results),
            fused_results=len(fused),
            query_preview=query_text[:80],
        )
        return fused

    # ── Dense (pgvector) ──────────────────────────────────────────────────────

    async def _vector_search(
        self,
        query_vector: list[float],
        n: int,
        jurisdiction: str | None,
        case_type: str | None,
    ) -> list[SearchResult]:
        conn = await self._get_conn()
        clauses = []
        params: list[Any] = [query_vector, n]

        if jurisdiction:
            clauses.append(f"metadata->>'jurisdiction' = ${len(params) + 1}")
            params.append(jurisdiction)
        if case_type:
            clauses.append(f"metadata->>'case_type' = ${len(params) + 1}")
            params.append(case_type)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        sql = f"""
            SELECT chunk_id, source_id, content, section, citations, metadata,
                   1 - (embedding <=> $1::vector) AS score
            FROM legal_chunks
            {where}
            ORDER BY embedding <=> $1::vector
            LIMIT $2;
        """

        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()

        return [
            SearchResult(
                chunk_id=row[0],
                source_id=row[1],
                content=row[2],
                section=row[3] or "",
                citations=row[4] or [],
                metadata=row[5] or {},
                score=float(row[6]),
            )
            for row in rows
        ]

    # ── Sparse (BM25 over dense candidates) ──────────────────────────────────

    @staticmethod
    def _bm25_search(
        candidates: list[SearchResult],
        query: str,
        n: int,
    ) -> list[SearchResult]:
        if not candidates:
            return []

        tokenized_corpus = [r.content.lower().split() for r in candidates]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query.lower().split())

        ranked = sorted(
            zip(candidates, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return [r for r, _ in ranked[:n]]

    # ── RRF fusion ────────────────────────────────────────────────────────────

    def _reciprocal_rank_fusion(
        self,
        dense: list[SearchResult],
        sparse: list[SearchResult],
        k: int,
    ) -> list[SearchResult]:
        """
        RRF score = Σ 1 / (rrf_k + rank_i)
        Combines dense and sparse rank lists; returns top-k by fused score.
        """
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, SearchResult] = {}

        for rank, result in enumerate(dense, start=1):
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + 1 / (
                self._rrf_k + rank
            )
            chunk_map[result.chunk_id] = result

        for rank, result in enumerate(sparse, start=1):
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + 1 / (
                self._rrf_k + rank
            )
            chunk_map[result.chunk_id] = result

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        results = []
        for cid in sorted_ids[:k]:
            r = chunk_map[cid]
            r.score = rrf_scores[cid]
            results.append(r)
        return results

    # ── Connection ────────────────────────────────────────────────────────────

    async def _get_conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            import psycopg  # noqa: PLC0415
            from pgvector.psycopg import register_vector  # noqa: PLC0415
            self._conn = await psycopg.AsyncConnection.connect(self._database_url)
            await register_vector(self._conn)
        return self._conn
