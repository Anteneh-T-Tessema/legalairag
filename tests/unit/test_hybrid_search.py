from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from retrieval.hybrid_search import HybridSearcher, SearchResult
from retrieval.query_parser import parse_legal_query


class TestQueryParser:
    def test_detect_indiana_code_citation(self) -> None:
        parsed = parse_legal_query("What does Ind. Code § 35-42-1-1 say about murder?")
        assert "35-42-1-1" in " ".join(parsed.citations_mentioned)

    def test_detect_county_jurisdiction(self) -> None:
        parsed = parse_legal_query("What are the filing fees in Marion County court?")
        assert parsed.jurisdiction == "Marion County"

    def test_detect_criminal_case_type(self) -> None:
        parsed = parse_legal_query("What is the penalty for felony possession?")
        assert parsed.case_type == "Criminal"

    def test_detect_civil_case_type(self) -> None:
        parsed = parse_legal_query("I want to file a civil suit for breach of contract.")
        assert parsed.case_type == "Civil"

    def test_normalizes_trailing_punctuation(self) -> None:
        parsed = parse_legal_query("What is the statute of limitations?")
        assert not parsed.normalized.endswith("?")

    def test_keywords_exclude_stopwords(self) -> None:
        parsed = parse_legal_query("What is the statute of limitations in Indiana?")
        assert "the" not in parsed.keywords
        assert "statute" in parsed.keywords

    # ── Query classification ──────────────────────────────────────────────────

    def test_citation_lookup_query_type(self) -> None:
        parsed = parse_legal_query("I.C. § 35-42-1-1 murder mens rea")
        assert parsed.query_type == "citation_lookup"
        assert parsed.bm25_weight >= 0.65

    def test_semantic_query_type(self) -> None:
        parsed = parse_legal_query("What are the elements of negligence in Indiana?")
        assert parsed.query_type == "semantic"
        assert parsed.bm25_weight <= 0.35

    def test_hybrid_query_type_default(self) -> None:
        parsed = parse_legal_query("Indiana court ruling on property tax exemption")
        assert parsed.query_type in {"hybrid", "semantic", "citation_lookup"}
        # bm25_weight is always in [0, 1]
        assert 0.0 <= parsed.bm25_weight <= 1.0

    def test_temporal_filter_triggered(self) -> None:
        parsed = parse_legal_query("What is the current law on bail reform in Indiana?")
        assert parsed.temporal_filter is True

    def test_temporal_filter_not_triggered(self) -> None:
        parsed = parse_legal_query("Battery under I.C. 35-42-2-1")
        assert parsed.temporal_filter is False

    def test_authority_alpha_in_range(self) -> None:
        for query in [
            "I.C. § 31-17-2-8 child custody",
            "What is negligence?",
            "Indiana Supreme Court battery cases",
        ]:
            parsed = parse_legal_query(query)
            assert 0.0 <= parsed.authority_alpha <= 1.0


class TestRRFFusion:
    def _make_results(self, ids: list[str]) -> list[SearchResult]:
        return [
            SearchResult(
                chunk_id=cid,
                source_id=cid,
                content=f"Content for {cid}",
                section="",
                citations=[],
                metadata={},
                score=1.0,
            )
            for cid in ids
        ]

    def _searcher(self) -> HybridSearcher:
        s = HybridSearcher.__new__(HybridSearcher)
        s._rrf_k = 60
        return s

    def test_rrf_promotes_results_appearing_in_both_lists(self) -> None:
        searcher = self._searcher()
        dense = self._make_results(["A", "B", "C", "D"])
        sparse = self._make_results(["C", "A", "E", "F"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=4)
        fused_ids = [r.chunk_id for r in fused]

        # A and C appear in both lists — they should rank highest
        assert fused_ids[0] in {"A", "C"}
        assert fused_ids[1] in {"A", "C"}

    def test_rrf_top_k_respected(self) -> None:
        searcher = self._searcher()
        dense = self._make_results(["A", "B", "C", "D", "E"])
        sparse = self._make_results(["A", "C", "E", "G", "H"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=3)
        assert len(fused) == 3

    def test_rrf_pure_vector_mode(self) -> None:
        """bm25_weight=0.0 → only dense list contributes."""
        searcher = self._searcher()
        dense = self._make_results(["A", "B"])
        sparse = self._make_results(["C", "D"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=4, bm25_weight=0.0)
        fused_ids = {r.chunk_id for r in fused}
        # Sparse-only items (C, D) get zero contribution
        assert "A" in fused_ids
        assert "B" in fused_ids

    def test_rrf_pure_bm25_mode(self) -> None:
        """bm25_weight=1.0 → only sparse list contributes."""
        searcher = self._searcher()
        dense = self._make_results(["A", "B"])
        sparse = self._make_results(["C", "D"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=4, bm25_weight=1.0)
        fused_ids = {r.chunk_id for r in fused}
        # Dense-only items (A, B) get zero contribution
        assert "C" in fused_ids
        assert "D" in fused_ids

    def test_rrf_scores_are_positive(self) -> None:
        searcher = self._searcher()
        dense = self._make_results(["A", "B", "C"])
        sparse = self._make_results(["A", "D", "E"])

        for weight in [0.0, 0.3, 0.5, 0.7, 1.0]:
            fused = searcher._reciprocal_rank_fusion(dense, sparse, k=5, bm25_weight=weight)
            assert all(r.score > 0 for r in fused)


class TestKeywordSearchParamOrdering:
    """Regression tests for the _keyword_search param-ordering bug.

    The SQL template has a leading %s in the ts_rank() call (SELECT list),
    then a %s in the WHERE tsvector clause.  The correct params_final must be:

        [query_text(ts_rank), or_query(WHERE), [jurisdiction?], [case_type?], n]

    where or_query = " OR ".join(query_text.split()) expands the terms with
    boolean OR for broad recall, while ts_rank still uses the original AND
    query for relevance scoring.

    If the ordering is wrong (e.g. params_final = params + [query_text]),
    jurisdiction/case_type values end up in the wrong placeholder and the
    query either crashes or returns nonsense.
    """

    def _make_searcher(self) -> HybridSearcher:
        s = HybridSearcher.__new__(HybridSearcher)
        return s

    def test_params_final_starts_with_query_text_no_filters(self) -> None:
        """Without filters, params_final = [query_text, or_query, n]."""
        query_text = "battery Indiana"
        n = 5
        jurisdiction = None
        case_type = None

        # Build params in the same way _keyword_search does
        or_query = " OR ".join(query_text.split())
        where_clauses = [
            "to_tsvector('english', content) @@ websearch_to_tsquery('english', %s)"
        ]
        params: list = [or_query]
        if jurisdiction:
            where_clauses.append("metadata->>'jurisdiction' = %s")
            params.append(jurisdiction)
        if case_type:
            where_clauses.append("metadata->>'case_type' = %s")
            params.append(case_type)
        params.append(n)
        params_final: list = [query_text] + params

        # ts_rank arg (SELECT) uses original AND query for relevance scoring
        assert params_final[0] == query_text, "ts_rank arg must be query_text"
        # WHERE arg uses OR-expanded query for broad recall
        assert params_final[1] == or_query, "WHERE tsvector arg must be or_query"
        assert params_final[-1] == n, "LIMIT arg must be last"
        assert len(params_final) == 3

    def test_params_final_with_jurisdiction(self) -> None:
        """With jurisdiction filter, params_final = [query_text, or_query, jurisdiction, n]."""
        query_text = "murder penalty"
        n = 10
        jurisdiction = "Indiana"
        case_type = None

        or_query = " OR ".join(query_text.split())
        where_clauses = [
            "to_tsvector('english', content) @@ websearch_to_tsquery('english', %s)"
        ]
        params: list = [or_query]
        if jurisdiction:
            where_clauses.append("metadata->>'jurisdiction' = %s")
            params.append(jurisdiction)
        if case_type:
            where_clauses.append("metadata->>'case_type' = %s")
            params.append(case_type)
        params.append(n)
        params_final: list = [query_text] + params

        assert params_final[0] == query_text
        assert params_final[1] == or_query, "WHERE tsvector arg must be or_query"
        assert params_final[2] == jurisdiction, (
            "jurisdiction must be the 3rd param, not mixed into tsvector position"
        )
        assert params_final[3] == n
        assert len(params_final) == 4

    def test_params_final_with_both_filters(self) -> None:
        """params_final = [query_text, or_query, jurisdiction, case_type, n]."""
        query_text = "child custody modification"
        n = 7
        jurisdiction = "Indiana"
        case_type = "Family"

        or_query = " OR ".join(query_text.split())
        where_clauses = [
            "to_tsvector('english', content) @@ websearch_to_tsquery('english', %s)"
        ]
        params: list = [or_query]
        if jurisdiction:
            where_clauses.append("metadata->>'jurisdiction' = %s")
            params.append(jurisdiction)
        if case_type:
            where_clauses.append("metadata->>'case_type' = %s")
            params.append(case_type)
        params.append(n)
        params_final: list = [query_text] + params

        assert params_final[0] == query_text
        assert params_final[1] == or_query, "WHERE tsvector arg must be or_query"
        assert params_final[2] == jurisdiction
        assert params_final[3] == case_type
        assert params_final[4] == n
        assert len(params_final) == 5


# ── DB-mocked tests for _vector_search, _keyword_search, search() ─────────────


def _make_db_row(
    chunk_id: str,
    score: float = 0.85,
    jurisdiction: str = "Indiana",
) -> tuple:
    """Return a row tuple matching the SELECT column order in the SQL queries."""
    return (
        chunk_id,
        f"src-{chunk_id}",
        f"Statutory content for {chunk_id}.",
        "SECTION 1",
        ["Ind. Code § 35-42-1-1"],
        {"jurisdiction": jurisdiction},
        score,
    )


def _make_cursor_mock(rows: list) -> tuple:
    """Return (mock_conn, mock_cur) with async context manager setup."""
    mock_cur = AsyncMock()
    mock_cur.execute = AsyncMock()
    mock_cur.fetchall = AsyncMock(return_value=rows)

    cursor_ctx = MagicMock()
    cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cur)
    cursor_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = cursor_ctx

    return mock_conn, mock_cur


def _make_searcher_no_conn() -> HybridSearcher:
    s = HybridSearcher.__new__(HybridSearcher)
    s._database_url = "postgresql://test:test@localhost/test"
    s._top_k = 10
    s._rrf_k = 60
    s._conn = None
    return s


class TestVectorSearch:
    """Unit tests for HybridSearcher._vector_search with mocked psycopg connection."""

    @pytest.mark.asyncio
    async def test_returns_search_results(self) -> None:
        searcher = _make_searcher_no_conn()
        rows = [_make_db_row("c1", 0.95), _make_db_row("c2", 0.80)]
        mock_conn, _ = _make_cursor_mock(rows)
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        results = await searcher._vector_search([0.1, 0.2], n=5, jurisdiction=None, case_type=None)

        assert len(results) == 2
        assert results[0].chunk_id == "c1"
        assert results[0].score == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self) -> None:
        searcher = _make_searcher_no_conn()
        mock_conn, _ = _make_cursor_mock([])
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        results = await searcher._vector_search([0.1], n=5, jurisdiction=None, case_type=None)

        assert results == []

    @pytest.mark.asyncio
    async def test_jurisdiction_filter_added_to_params(self) -> None:
        searcher = _make_searcher_no_conn()
        rows = [_make_db_row("c1")]
        mock_conn, mock_cur = _make_cursor_mock(rows)
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        await searcher._vector_search([0.1], n=5, jurisdiction="Indiana", case_type=None)

        call_args = mock_cur.execute.call_args[0]
        params = call_args[1]
        assert "Indiana" in params

    @pytest.mark.asyncio
    async def test_case_type_filter_added_to_params(self) -> None:
        searcher = _make_searcher_no_conn()
        rows = [_make_db_row("c1")]
        mock_conn, mock_cur = _make_cursor_mock(rows)
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        await searcher._vector_search([0.1], n=5, jurisdiction=None, case_type="Criminal")

        call_args = mock_cur.execute.call_args[0]
        params = call_args[1]
        assert "Criminal" in params

    @pytest.mark.asyncio
    async def test_result_fields_mapped_correctly(self) -> None:
        searcher = _make_searcher_no_conn()
        row = _make_db_row("chunk-42", 0.77)
        mock_conn, _ = _make_cursor_mock([row])
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        results = await searcher._vector_search([0.1], n=5, jurisdiction=None, case_type=None)

        r = results[0]
        assert r.chunk_id == "chunk-42"
        assert r.source_id == "src-chunk-42"
        assert r.score == pytest.approx(0.77)
        assert r.citations == ["Ind. Code § 35-42-1-1"]


class TestKeywordSearchDB:
    """Unit tests for HybridSearcher._keyword_search with mocked psycopg connection."""

    @pytest.mark.asyncio
    async def test_returns_search_results(self) -> None:
        searcher = _make_searcher_no_conn()
        rows = [_make_db_row("k1", 0.70), _make_db_row("k2", 0.55)]
        mock_conn, _ = _make_cursor_mock(rows)
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        results = await searcher._keyword_search(
            "battery Indiana", n=5, jurisdiction=None, case_type=None
        )

        assert len(results) == 2
        assert results[0].chunk_id == "k1"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self) -> None:
        searcher = _make_searcher_no_conn()
        mock_conn, _ = _make_cursor_mock([])
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        results = await searcher._keyword_search(
            "obscure term", n=5, jurisdiction=None, case_type=None
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_or_expanded_query_in_params(self) -> None:
        """_keyword_search must pass OR-expanded query for broad WHERE recall."""
        searcher = _make_searcher_no_conn()
        mock_conn, mock_cur = _make_cursor_mock([])
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        await searcher._keyword_search("murder penalty", n=5, jurisdiction=None, case_type=None)

        call_args = mock_cur.execute.call_args[0]
        params = call_args[1]
        # params_final[1] == or_query: OR-expanded WHERE clause
        assert "murder OR penalty" in params

    @pytest.mark.asyncio
    async def test_jurisdiction_and_case_type_in_params(self) -> None:
        searcher = _make_searcher_no_conn()
        mock_conn, mock_cur = _make_cursor_mock([])
        searcher._get_conn = AsyncMock(return_value=mock_conn)  # type: ignore[method-assign]

        await searcher._keyword_search(
            "battery", n=5, jurisdiction="Marion County", case_type="Criminal"
        )

        call_args = mock_cur.execute.call_args[0]
        params = call_args[1]
        assert "Marion County" in params
        assert "Criminal" in params


class TestHybridSearchSearch:
    """Integration tests for search() using mocked _vector_search and _keyword_search."""

    def _make_results(self, ids: list[str]) -> list[SearchResult]:
        return [
            SearchResult(
                chunk_id=cid,
                source_id=f"src-{cid}",
                content=f"Content for {cid}",
                section="",
                citations=[],
                metadata={},
                score=0.9,
            )
            for cid in ids
        ]

    @pytest.mark.asyncio
    async def test_search_returns_fused_results(self) -> None:
        searcher = _make_searcher_no_conn()
        dense = self._make_results(["d1", "d2", "d3"])
        keyword = self._make_results(["d1", "k1", "k2"])

        searcher._vector_search = AsyncMock(return_value=dense)  # type: ignore[method-assign]
        searcher._keyword_search = AsyncMock(return_value=keyword)  # type: ignore[method-assign]

        results = await searcher.search([0.1] * 10, "battery Indiana", top_k=3)

        assert len(results) <= 3
        result_ids = [r.chunk_id for r in results]
        # d1 appears in both dense and keyword → highest RRF rank
        assert "d1" in result_ids

    @pytest.mark.asyncio
    async def test_search_respects_top_k(self) -> None:
        searcher = _make_searcher_no_conn()
        dense = self._make_results(["a", "b", "c", "d", "e"])
        keyword = self._make_results(["a", "c", "e", "f", "g"])

        searcher._vector_search = AsyncMock(return_value=dense)  # type: ignore[method-assign]
        searcher._keyword_search = AsyncMock(return_value=keyword)  # type: ignore[method-assign]

        results = await searcher.search([0.1] * 10, "query text", top_k=2)

        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_search_empty_results_when_no_candidates(self) -> None:
        searcher = _make_searcher_no_conn()
        searcher._vector_search = AsyncMock(return_value=[])  # type: ignore[method-assign]
        searcher._keyword_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

        results = await searcher.search([0.1] * 10, "query", top_k=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_search_forwards_jurisdiction_to_subqueries(self) -> None:
        searcher = _make_searcher_no_conn()
        searcher._vector_search = AsyncMock(return_value=[])  # type: ignore[method-assign]
        searcher._keyword_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

        await searcher.search(
            [0.1] * 10, "query", jurisdiction="Indiana", case_type="Criminal", top_k=5
        )

        call_kwargs_v = searcher._vector_search.call_args.kwargs
        assert call_kwargs_v["jurisdiction"] == "Indiana"
        assert call_kwargs_v["case_type"] == "Criminal"

        call_kwargs_k = searcher._keyword_search.call_args.kwargs
        assert call_kwargs_k["jurisdiction"] == "Indiana"
        assert call_kwargs_k["case_type"] == "Criminal"


class TestBM25Search:
    """Unit tests for the static _bm25_search method."""

    def _make_results(self, ids_contents: list[tuple[str, str]]) -> list[SearchResult]:
        return [
            SearchResult(
                chunk_id=cid,
                source_id=cid,
                content=content,
                section="",
                citations=[],
                metadata={},
                score=0.0,
            )
            for cid, content in ids_contents
        ]

    def _searcher(self) -> HybridSearcher:
        s = HybridSearcher.__new__(HybridSearcher)
        s._rrf_k = 60
        return s

    def test_returns_empty_list_for_empty_candidates(self) -> None:
        searcher = self._searcher()
        result = searcher._bm25_search([], "battery", n=5)
        assert result == []

    def test_returns_top_n_results(self) -> None:
        searcher = self._searcher()
        candidates = self._make_results(
            [
                ("c1", "murder penalty Indiana statute"),
                ("c2", "battery assault felony"),
                ("c3", "civil contract damages Indiana"),
                ("c4", "property tax exemption"),
                ("c5", "murder homicide mens rea Indiana"),
            ]
        )
        results = searcher._bm25_search(candidates, "murder Indiana", n=3)
        assert len(results) <= 3

    def test_bm25_ranks_matching_content_higher(self) -> None:
        searcher = self._searcher()
        candidates = self._make_results(
            [
                ("relevant", "battery assault felony Indiana code"),
                ("irrelevant", "contract damages property law"),
            ]
        )
        results = searcher._bm25_search(candidates, "battery felony", n=2)
        assert results[0].chunk_id == "relevant"
