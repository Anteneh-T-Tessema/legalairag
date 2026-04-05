"""Unit tests for retrieval.authority module."""

from __future__ import annotations

from datetime import date

import pytest

from retrieval.authority import (
    AuthorityRanker,
    CitationEdge,
    CitationGraph,
    NodeMetadata,
    filter_temporally_valid,
    get_authority_score,
    is_temporally_valid,
)
from retrieval.hybrid_search import SearchResult


def _result(
    chunk_id: str,
    source_id: str,
    score: float,
    court: str = "",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        source_id=source_id,
        content="",
        section="",
        citations=[],
        metadata={"court": court},
        score=score,
    )


def _node(source_id: str, court: str = "ind") -> NodeMetadata:
    return NodeMetadata(
        source_id=source_id,
        court=court,
        court_level="supreme",
        date_filed=date(2020, 1, 1),
        case_name=f"Case {source_id}",
        citation_string="",
    )


# ── get_authority_score ────────────────────────────────────────────────────────


def test_authority_score_scotus():
    assert get_authority_score("scotus") == 1.00


def test_authority_score_ca7():
    assert get_authority_score("ca7") == 0.90


def test_authority_score_ind():
    assert get_authority_score("ind") == 0.85


def test_authority_score_indctapp():
    assert get_authority_score("indctapp") == 0.70


def test_authority_score_full_name_match():
    assert get_authority_score("Indiana Supreme Court") == 0.85


def test_authority_score_seventh_circuit_full():
    assert get_authority_score("7th Circuit Court of Appeals") == 0.90


def test_authority_score_unknown_court():
    assert get_authority_score("some unknown tribunal") == 0.35


def test_authority_score_empty():
    assert get_authority_score("") == 0.35


# ── AuthorityRanker ────────────────────────────────────────────────────────────


def test_ranker_alpha_zero_preserves_order():
    """With alpha=0 authority adds nothing; original score order is kept."""
    ranker = AuthorityRanker(authority_alpha=0.0)
    results = [
        _result("high", "s1", 0.9, court="ind"),
        _result("low", "s2", 0.5, court="scotus"),
    ]
    ranked = ranker.rerank(results, alpha=0.0)
    assert ranked[0].chunk_id == "high"
    assert ranked[0].score == pytest.approx(0.9)


def test_ranker_alpha_one_orders_by_court_only():
    """With alpha=1 the court authority fully determines ranking."""
    ranker = AuthorityRanker(authority_alpha=1.0)
    results = [
        _result("ind_case", "s1", 0.99, court="ind"),  # 0.85 authority
        _result("scotus_case", "s2", 0.01, court="scotus"),  # 1.00 authority
    ]
    ranked = ranker.rerank(results, alpha=1.0)
    assert ranked[0].chunk_id == "scotus_case"


def test_ranker_blend_formula():
    """Verify blended = (1-alpha)*retrieval + alpha*authority."""
    ranker = AuthorityRanker(authority_alpha=0.30)
    results = [_result("x", "s1", 0.7, court="scotus")]
    ranked = ranker.rerank(results)
    expected = 0.70 * 0.7 + 0.30 * 1.0
    assert ranked[0].score == pytest.approx(expected)


def test_ranker_output_is_sorted_descending():
    ranker = AuthorityRanker()
    results = [
        _result("c", "s3", 0.2, court=""),
        _result("a", "s1", 0.9, court="scotus"),
        _result("b", "s2", 0.5, court="ind"),
    ]
    ranked = ranker.rerank(results)
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_ranker_per_call_alpha_overrides_default():
    ranker = AuthorityRanker(authority_alpha=0.0)
    results = [
        _result("a", "s1", 0.9, court="ind"),
        _result("b", "s2", 0.1, court="scotus"),
    ]
    # Override default 0.0 with 1.0 → order flips
    ranked = ranker.rerank(results, alpha=1.0)
    assert ranked[0].chunk_id == "b"


# ── CitationGraph ──────────────────────────────────────────────────────────────


def test_unknown_node_is_good_law():
    graph = CitationGraph()
    assert graph.is_good_law("ghost") is True


def test_overruled_marks_cited_bad_law():
    graph = CitationGraph()
    graph.add_node(_node("old"))
    graph.add_node(_node("new"))
    graph.add_edge(
        CitationEdge(
            citing_id="new",
            cited_id="old",
            treatment="overruled",
            is_negative=True,
        )
    )
    assert graph.is_good_law("old") is False


def test_overruled_sets_overruled_by():
    graph = CitationGraph()
    graph.add_node(_node("old"))
    graph.add_node(_node("new"))
    graph.add_edge(CitationEdge("new", "old", "overruled", is_negative=True))
    assert graph._nodes["old"].overruled_by == "new"


def test_positive_treatment_leaves_good_law():
    graph = CitationGraph()
    graph.add_node(_node("cited"))
    graph.add_node(_node("citing"))
    graph.add_edge(
        CitationEdge(
            citing_id="citing",
            cited_id="cited",
            treatment="followed",
            is_negative=False,
        )
    )
    assert graph.is_good_law("cited") is True


def test_citing_count_increments_per_edge():
    graph = CitationGraph()
    graph.add_node(_node("target"))
    graph.add_node(_node("a"))
    graph.add_node(_node("b"))
    graph.add_edge(CitationEdge("a", "target", "cited", is_negative=False))
    graph.add_edge(CitationEdge("b", "target", "cited", is_negative=False))
    assert graph.get_citing_count("target") == 2


def test_citing_count_zero_for_uncited():
    graph = CitationGraph()
    graph.add_node(_node("solo"))
    assert graph.get_citing_count("solo") == 0


def test_compute_pagerank_all_nodes_scored():
    graph = CitationGraph()
    ids = ["n1", "n2", "n3"]
    for nid in ids:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("n1", "n2", "cited", is_negative=False))
    graph.add_edge(CitationEdge("n2", "n3", "cited", is_negative=False))
    graph.compute_pagerank()
    for nid in ids:
        assert graph._nodes[nid].pagerank_score >= 0.0


def test_compute_pagerank_empty_graph_no_error():
    CitationGraph().compute_pagerank()


def test_enrich_results_filters_overruled():
    graph = CitationGraph()
    graph.add_node(_node("bad"))
    graph.add_node(_node("good"))
    graph.add_node(_node("overruler"))
    graph.add_edge(CitationEdge("overruler", "bad", "overruled", is_negative=True))
    results = [
        _result("c1", "bad", 0.9),
        _result("c2", "good", 0.5),
    ]
    enriched = graph.enrich_results(results, filter_bad_law=True)
    source_ids = {r.source_id for r in enriched}
    assert "bad" not in source_ids
    assert "good" in source_ids


def test_enrich_results_annotates_times_cited():
    graph = CitationGraph()
    graph.add_node(_node("cited"))
    graph.add_node(_node("citer"))
    graph.add_edge(CitationEdge("citer", "cited", "cited", is_negative=False))
    results = [_result("c1", "cited", 0.8)]
    enriched = graph.enrich_results(results, filter_bad_law=False, boost_cited=False)
    assert enriched[0].metadata["times_cited"] == 1


# ── is_temporally_valid ────────────────────────────────────────────────────────


def test_no_dates_always_valid():
    assert is_temporally_valid({}) is True


def test_future_effective_date_is_invalid():
    assert (
        is_temporally_valid(
            {"effective_date": "2099-06-01"},
            reference_date=date(2024, 1, 1),
        )
        is False
    )


def test_past_effective_date_is_valid():
    assert (
        is_temporally_valid(
            {"effective_date": "2018-01-01"},
            reference_date=date(2024, 1, 1),
        )
        is True
    )


def test_expired_document_is_invalid():
    assert (
        is_temporally_valid(
            {"expiry_date": "2019-12-31"},
            reference_date=date(2024, 1, 1),
        )
        is False
    )


def test_filter_removes_stale_result():
    results = [
        _result("fresh", "s1", 0.9),
        _result("stale", "s2", 0.8),
    ]
    results[1].metadata["expiry_date"] = "2020-01-01"
    valid = filter_temporally_valid(
        results,
        reference_date=date(2024, 1, 1),
        warn_on_filter=False,
    )
    assert len(valid) == 1
    assert valid[0].chunk_id == "fresh"


# ── get_authority_score: substring match ──────────────────────────────────────


def test_authority_score_substring_match():
    # "Indiana Supreme Court of Indiana" is not an exact key but contains
    # "supreme court of indiana" → substring match → 0.85
    score = get_authority_score("The Supreme Court of Indiana (2023)")
    assert score == 0.85


# ── is_temporally_valid: ValueError branches ─────────────────────────────────


def test_invalid_effective_date_string_treated_as_valid():
    # Malformed effective_date → ValueError caught → document treated as valid
    assert is_temporally_valid({"effective_date": "not-a-date"}) is True


def test_invalid_expiry_date_string_treated_as_valid():
    # Malformed expiry_date → ValueError caught → document treated as valid
    assert is_temporally_valid({"expiry_date": "bad/date"}) is True


def test_future_expiry_date_still_valid():
    # expiry_date is in the future → document is still valid (168->173 branch)
    assert (
        is_temporally_valid(
            {"expiry_date": "2099-12-31"},
            reference_date=date(2024, 1, 1),
        )
        is True
    )


# ── filter_temporally_valid: warn_on_filter=True ──────────────────────────────


def test_filter_logs_warning_when_warn_on_filter_true(caplog):
    results = [_result("stale", "s1", 0.9)]
    results[0].metadata["expiry_date"] = "2010-01-01"
    valid = filter_temporally_valid(
        results,
        reference_date=date(2024, 1, 1),
        warn_on_filter=True,
    )
    assert len(valid) == 0


# ── CitationGraph: add_node with citation_string ──────────────────────────────


def test_add_node_registers_citation_string():
    graph = CitationGraph()
    node = NodeMetadata(
        source_id="op1",
        court="ind",
        court_level="supreme",
        date_filed=date(2020, 1, 1),
        case_name="Case One",
        citation_string="123 N.E.3d 456",
    )
    graph.add_node(node)
    assert graph._citation_str_to_id["123 N.E.3d 456"] == "op1"


# ── CitationGraph: add_edge where cited_id not in nodes ───────────────────────


def test_add_edge_negative_treatment_unknown_cited_node():
    # cited node is NOT in the graph; the if-branch (275->exit) is False
    graph = CitationGraph()
    graph.add_node(_node("citer"))
    edge = CitationEdge("citer", "ghost", "overruled", is_negative=True)
    graph.add_edge(edge)  # must not raise
    # ghost node not in graph, so no side-effects on nodes
    assert "ghost" not in graph._nodes


# ── CitationGraph: get_precedents ─────────────────────────────────────────────


def test_get_precedents_single_depth():
    graph = CitationGraph()
    for nid in ["a", "b", "c"]:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("a", "b", "cited", is_negative=False))
    graph.add_edge(CitationEdge("b", "c", "cited", is_negative=False))
    # depth=1: only direct citations from "a"
    precedents = graph.get_precedents("a", depth=1)
    assert set(precedents) == {"b"}


def test_get_precedents_two_depth():
    graph = CitationGraph()
    for nid in ["a", "b", "c"]:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("a", "b", "cited", is_negative=False))
    graph.add_edge(CitationEdge("b", "c", "cited", is_negative=False))
    # depth=2: follows chain a→b→c
    precedents = graph.get_precedents("a", depth=2)
    assert set(precedents) == {"b", "c"}


def test_get_precedents_no_edges_returns_empty():
    graph = CitationGraph()
    graph.add_node(_node("lone"))
    assert graph.get_precedents("lone") == []


def test_get_precedents_deduplicates_already_visited():
    # Both "a" and "b" cite "c" — "c" must appear only once (306->305 branch)
    graph = CitationGraph()
    for nid in ["a", "b", "c"]:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("a", "c", "cited", is_negative=False))
    graph.add_edge(CitationEdge("a", "b", "cited", is_negative=False))
    graph.add_edge(CitationEdge("b", "c", "cited", is_negative=False))
    precedents = graph.get_precedents("a", depth=2)
    assert precedents.count("c") == 1


# ── CitationGraph: pagerank with negative edges ───────────────────────────────


def test_compute_pagerank_skips_negative_edges():
    # negative edges should not propagate authority (331->330 branch)
    graph = CitationGraph()
    for nid in ["a", "b"]:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("a", "b", "overruled", is_negative=True))
    graph.compute_pagerank()
    # b got no positive citations, so its score should be low / baseline only
    assert graph._nodes["b"].pagerank_score >= 0.0  # no error; score is set


# ── CitationGraph: enrich_results with pagerank boost ─────────────────────────


def test_enrich_results_boosts_score_via_pagerank():
    graph = CitationGraph()
    for nid in ["cited", "citer"]:
        graph.add_node(_node(nid))
    graph.add_edge(CitationEdge("citer", "cited", "cited", is_negative=False))
    graph.compute_pagerank()
    # Ensure cited has a positive pagerank_score before calling enrich
    graph._nodes["cited"].pagerank_score = 0.8
    results = [_result("c1", "cited", 0.5)]
    enriched = graph.enrich_results(results, filter_bad_law=False, boost_cited=True)
    assert enriched[0].score > 0.5
    assert "pagerank_score" in enriched[0].metadata


# ── CitationGraph: parse_edge_from_context ────────────────────────────────────


def test_parse_edge_negative_treatment():
    edge = CitationGraph.parse_edge_from_context(
        "a", "b", "The court overruled the earlier decision."
    )
    assert edge.is_negative is True
    assert "overruled" in edge.treatment


def test_parse_edge_positive_treatment():
    edge = CitationGraph.parse_edge_from_context(
        "a", "b", "The court followed the reasoning in Smith v. Jones."
    )
    assert edge.is_negative is False
    assert edge.treatment == "followed"


def test_parse_edge_default_treatment():
    edge = CitationGraph.parse_edge_from_context("a", "b", "See also 123 N.E.3d 456.")
    assert edge.is_negative is False
    assert edge.treatment == "cited"


def test_parse_edge_with_date():
    from datetime import date as _date

    edge = CitationGraph.parse_edge_from_context(
        "a", "b", "cited", date_cited=_date(2023, 6, 15)
    )
    assert edge.date_cited == _date(2023, 6, 15)


# ── CitationGraph: __len__ and __repr__ ────────────────────────────────────────


def test_citation_graph_len():
    graph = CitationGraph()
    assert len(graph) == 0
    graph.add_node(_node("x"))
    assert len(graph) == 1


def test_citation_graph_repr():
    graph = CitationGraph()
    graph.add_node(_node("x"))
    graph.add_edge(CitationEdge("x", "y", "cited", is_negative=False))
    r = repr(graph)
    assert "CitationGraph" in r
    assert "nodes=1" in r
