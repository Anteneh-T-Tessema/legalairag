from __future__ import annotations

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

    def test_rrf_promotes_results_appearing_in_both_lists(self) -> None:
        searcher = HybridSearcher.__new__(HybridSearcher)
        searcher._rrf_k = 60

        dense = self._make_results(["A", "B", "C", "D"])
        sparse = self._make_results(["C", "A", "E", "F"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=4)
        fused_ids = [r.chunk_id for r in fused]

        # A and C appear in both lists — they should rank highest
        assert fused_ids[0] in {"A", "C"}
        assert fused_ids[1] in {"A", "C"}

    def test_rrf_top_k_respected(self) -> None:
        searcher = HybridSearcher.__new__(HybridSearcher)
        searcher._rrf_k = 60

        dense = self._make_results(["A", "B", "C", "D", "E"])
        sparse = self._make_results(["A", "C", "E", "G", "H"])

        fused = searcher._reciprocal_rank_fusion(dense, sparse, k=3)
        assert len(fused) == 3
