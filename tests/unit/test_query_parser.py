"""Unit tests for retrieval.query_parser — legal query parsing & classification."""

from __future__ import annotations

from retrieval.query_parser import (
    ParsedQuery,
    _classify_query,
    _detect_case_type,
    _detect_jurisdiction,
    _extract_keywords,
    _needs_temporal_filter,
    _normalize_query,
    parse_legal_query,
)

# ── parse_legal_query (integration-level) ────────────────────────────────────


class TestParseLegalQuery:
    def test_returns_parsed_query(self) -> None:
        pq = parse_legal_query("What is Indiana Code § 35-42-1-1?")
        assert isinstance(pq, ParsedQuery)
        assert pq.raw.startswith("What")

    def test_detects_jurisdiction_and_citation(self) -> None:
        pq = parse_legal_query("Indiana Code § 35-42-1-1 penalties")
        assert pq.jurisdiction is not None
        assert len(pq.citations_mentioned) >= 1

    def test_semantic_query_classification(self) -> None:
        pq = parse_legal_query("What are the penalties for theft in Indiana?")
        assert pq.query_type == "semantic"
        assert pq.bm25_weight < 0.5

    def test_citation_lookup_classification(self) -> None:
        pq = parse_legal_query("Indiana Code § 35-42-1-1")
        assert pq.query_type == "citation_lookup"
        assert pq.bm25_weight > 0.5

    def test_hybrid_classification(self) -> None:
        pq = parse_legal_query("What does Indiana Code § 35-42-1-1 say about self-defense?")
        assert pq.query_type == "hybrid"

    def test_temporal_filter_set(self) -> None:
        pq = parse_legal_query("Is Indiana Code § 35-42-1-1 still in effect?")
        assert pq.temporal_filter is True

    def test_temporal_filter_not_set(self) -> None:
        pq = parse_legal_query("History of theft statutes in Indiana")
        assert pq.temporal_filter is False


# ── _detect_jurisdiction ─────────────────────────────────────────────────────


class TestDetectJurisdiction:
    def test_county_alias(self) -> None:
        assert _detect_jurisdiction("file in marion county") == "Marion County"

    def test_generic_indiana(self) -> None:
        assert _detect_jurisdiction("indiana law on theft") == "Indiana"

    def test_no_jurisdiction(self) -> None:
        assert _detect_jurisdiction("federal tax guidelines") is None


# ── _detect_case_type ────────────────────────────────────────────────────────


class TestDetectCaseType:
    def test_criminal_via_felony(self) -> None:
        assert _detect_case_type("felony charges") == "Criminal"

    def test_probate(self) -> None:
        assert _detect_case_type("estate planning") == "Probate"

    def test_no_match(self) -> None:
        assert _detect_case_type("other legal matters") is None


# ── _classify_query ──────────────────────────────────────────────────────────


class TestClassifyQuery:
    def test_citation_only(self) -> None:
        qt, bm25, alpha = _classify_query("I.C. § 35-42-1-1")
        assert qt == "citation_lookup"
        assert bm25 == 0.70

    def test_semantic_only(self) -> None:
        qt, bm25, alpha = _classify_query("What is the process for expungement?")
        assert qt == "semantic"
        assert bm25 == 0.30

    def test_mixed(self) -> None:
        qt, bm25, alpha = _classify_query("Explain I.C. § 35-42-1-1")
        assert qt == "hybrid"
        assert bm25 == 0.50


# ── _extract_keywords ────────────────────────────────────────────────────────


class TestExtractKeywords:
    def test_removes_stopwords(self) -> None:
        kw = _extract_keywords("What is the penalty for a felony in Indiana?")
        assert "the" not in kw
        assert "what" not in kw
        assert "penalty" in kw
        assert "felony" in kw

    def test_deduplicates(self) -> None:
        kw = _extract_keywords("penalty penalty penalty")
        assert kw.count("penalty") == 1

    def test_ignores_short_tokens(self) -> None:
        kw = _extract_keywords("It is ok to do so")
        # All tokens <= 2 chars get dropped
        assert kw == []


# ── _normalize_query ─────────────────────────────────────────────────────────


class TestNormalizeQuery:
    def test_collapses_whitespace(self) -> None:
        assert _normalize_query("  hello   world  ") == "hello world"

    def test_strips_trailing_punct(self) -> None:
        assert _normalize_query("what is theft?") == "what is theft"

    def test_preserves_inner_punct(self) -> None:
        assert "§" in _normalize_query("I.C. § 35-42-1-1")


# ── _needs_temporal_filter ───────────────────────────────────────────────────


class TestNeedsTemporalFilter:
    def test_current_triggers(self) -> None:
        assert _needs_temporal_filter("is this law still valid") is True

    def test_no_trigger(self) -> None:
        assert _needs_temporal_filter("history of legislation") is False
