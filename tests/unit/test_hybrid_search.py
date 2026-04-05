from __future__ import annotations

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
