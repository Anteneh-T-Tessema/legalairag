from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from config.logging import get_logger
from config.settings import settings

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

    Query-adaptive weighting:
    - Citation-lookup queries get higher BM25 weight (0.70)
    - Semantic queries get higher vector weight (bm25_weight=0.30)
    - Default: balanced (bm25_weight=0.50)

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
        bm25_weight: float = 0.5,
    ) -> list[SearchResult]:
        """
        Parameters
        ----------
        bm25_weight:  0.0 = pure vector, 1.0 = pure BM25.
                      Use ParsedQuery.bm25_weight for adaptive retrieval.
        """
        k = top_k or self._top_k
        candidate_n = min(k * 4, settings.rerank_top_k)

        dense_results = await self._vector_search(
            query_vector,
            n=candidate_n,
            jurisdiction=jurisdiction,
            case_type=case_type,
        )

        # In dev mode with hash-based embeddings, dense results may be semantically
        # irrelevant. Supplement with a full-text keyword search so BM25 can rank
        # documents that actually contain the query terms.
        keyword_results = await self._keyword_search(
            query_text,
            n=candidate_n,
            jurisdiction=jurisdiction,
            case_type=case_type,
        )

        # When keyword results exist, suppress the random-vector noise by routing
        # through BM25 only (bm25_weight=1.0). In production with real embeddings,
        # both components add value; in dev mode the dense vectors are hash-based
        # and semantically meaningless.
        effective_bm25_weight = bm25_weight
        if keyword_results and settings.app_env == "development":
            effective_bm25_weight = 1.0
            dense_results = keyword_results  # skip noisy vectors entirely
        else:
            # Merge, dedup by chunk_id
            seen: set[str] = {r.chunk_id for r in dense_results}
            for r in keyword_results:
                if r.chunk_id not in seen:
                    dense_results.append(r)
                    seen.add(r.chunk_id)

        sparse_results = self._bm25_search(dense_results, query_text, n=candidate_n)
        fused = self._reciprocal_rank_fusion(
            dense_results, sparse_results, k=k, bm25_weight=effective_bm25_weight
        )

        logger.info(
            "hybrid_search",
            dense_candidates=len(dense_results),
            fused_results=len(fused),
            bm25_weight=bm25_weight,
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
        where_clauses: list[str] = []
        where_params: list[Any] = []

        if jurisdiction:
            where_clauses.append("metadata->>'jurisdiction' = %s")
            where_params.append(jurisdiction)
        if case_type:
            where_clauses.append("metadata->>'case_type' = %s")
            where_params.append(case_type)

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT chunk_id, source_id, content, section, citations, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM legal_chunks
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        # Positional: SELECT vec, [where params], ORDER BY vec, LIMIT n
        params: list[Any] = [query_vector] + where_params + [query_vector, n]

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

    # ── Full-text keyword search (dev-mode supplement) ────────────────────────

    async def _keyword_search(
        self,
        query_text: str,
        n: int,
        jurisdiction: str | None,
        case_type: str | None,
    ) -> list[SearchResult]:
        """PostgreSQL full-text search over content — supplements vector search in dev mode."""
        conn = await self._get_conn()
        where_clauses = ["to_tsvector('english', content) @@ plainto_tsquery('english', %s)"]
        params: list[Any] = [query_text]

        if jurisdiction:
            where_clauses.append("metadata->>'jurisdiction' = %s")
            params.append(jurisdiction)
        if case_type:
            where_clauses.append("metadata->>'case_type' = %s")
            params.append(case_type)

        params.append(n)
        sql = f"""
            SELECT chunk_id, source_id, content, section, citations, metadata,
                   ts_rank(to_tsvector('english', content),
                           plainto_tsquery('english', %s)) AS score
            FROM legal_chunks
            WHERE {' AND '.join(where_clauses)}
            ORDER BY score DESC
            LIMIT %s;
        """
        # SQL order: ts_rank %s (SELECT), WHERE tsvector %s,
        # [WHERE jurisdiction %s], [WHERE case_type %s], LIMIT %s
        # params = [query_text, [jurisdiction?], [case_type?], n]
        params_final: list[Any] = [query_text] + params  # prepend ts_rank query_text

        async with conn.cursor() as cur:
            await cur.execute(sql, params_final)
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
            zip(candidates, scores, strict=False),
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
        bm25_weight: float = 0.5,
    ) -> list[SearchResult]:
        """
        Weighted RRF: score = (1-w)*dense_rrf + w*sparse_rrf

        bm25_weight=0.0 → pure vector (semantic queries)
        bm25_weight=1.0 → pure BM25  (citation-lookup queries)
        bm25_weight=0.5 → balanced   (default)
        """
        dense_weight = 1.0 - bm25_weight
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, SearchResult] = {}

        for rank, result in enumerate(dense, start=1):
            contrib = dense_weight / (self._rrf_k + rank)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + contrib
            chunk_map[result.chunk_id] = result

        for rank, result in enumerate(sparse, start=1):
            contrib = bm25_weight / (self._rrf_k + rank)
            rrf_scores[result.chunk_id] = rrf_scores.get(result.chunk_id, 0) + contrib
            chunk_map[result.chunk_id] = result

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        results = []
        for cid in sorted_ids[:k]:
            if rrf_scores[cid] <= 0:
                break  # remaining items have zero contribution; skip them
            r = chunk_map[cid]
            r.score = rrf_scores[cid]
            results.append(r)
        return results

    # ── Connection ────────────────────────────────────────────────────────────

    async def _get_conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            import psycopg  # noqa: PLC0415
            from pgvector.psycopg import register_vector_async  # noqa: PLC0415

            dsn = self._database_url.replace("+psycopg", "")
            self._conn = await psycopg.AsyncConnection.connect(dsn)
            await register_vector_async(self._conn)
        return self._conn
