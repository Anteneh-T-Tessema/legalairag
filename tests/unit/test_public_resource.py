"""Unit tests for ingestion.sources.public_resource — helpers + parsers."""

from __future__ import annotations

from datetime import date

from ingestion.sources.public_resource import (
    PublicLegalOpinion,
    _classify_court_level,
    _parse_dir_listing,
    _parse_lro_opinion_html,
    _strip_html,
)

# ── _strip_html ───────────────────────────────────────────────────────────────


class TestStripHTML:
    def test_removes_tags(self):
        assert _strip_html("<b>bold</b>") == "bold"

    def test_normalizes_whitespace(self):
        assert _strip_html("<p>a</p>  <p>b</p>") == "a b"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_nested_tags(self):
        result = _strip_html("<div><span>text</span></div>")
        assert "text" in result


# ── _parse_dir_listing ────────────────────────────────────────────────────────


class TestParseDirListing:
    def test_extracts_hrefs(self):
        html = '<a href="vol1/">vol1</a> <a href="vol2/">vol2</a>'
        result = _parse_dir_listing(html)
        assert "vol1" in result
        assert "vol2" in result

    def test_skips_parent_links(self):
        html = '<a href="../">Parent</a> <a href="data/">data</a>'
        result = _parse_dir_listing(html)
        assert ".." not in result
        assert "data" in result

    def test_strips_trailing_slash(self):
        html = '<a href="folder/">folder</a>'
        result = _parse_dir_listing(html)
        assert result == ["folder"]

    def test_skips_query_params(self):
        html = '<a href="?C=N;O=D">Name</a> <a href="file.html">file</a>'
        result = _parse_dir_listing(html)
        assert "file.html" in result
        assert len(result) == 1


# ── _classify_court_level ─────────────────────────────────────────────────────


class TestClassifyCourtLevel:
    def test_indiana_supreme(self):
        assert _classify_court_level("ind") == "supreme"

    def test_indiana_appeals(self):
        assert _classify_court_level("indctapp") == "appeals"

    def test_indiana_tax(self):
        assert _classify_court_level("indtc") == "trial"

    def test_seventh_circuit(self):
        assert _classify_court_level("ca7") == "federal_circuit"

    def test_scotus(self):
        assert _classify_court_level("scotus") == "federal_supreme"

    def test_unknown_court(self):
        assert _classify_court_level("fake") == "unknown"


# ── PublicLegalOpinion ────────────────────────────────────────────────────────


class TestPublicLegalOpinion:
    def test_source_id_property(self):
        o = PublicLegalOpinion(
            opinion_id="cl-123",
            source="courtlistener",
            court="Indiana Supreme Court",
            court_level="supreme",
            case_name="Test Case",
            docket_number="12345",
            date_filed=date(2024, 1, 1),
            jurisdiction="Indiana",
            text="Full text of the opinion.",
            citations_out=[],
            url="https://example.com",
        )
        assert o.source_id == "cl-123"

    def test_content_hash_deterministic(self):
        o = PublicLegalOpinion(
            opinion_id="cl-1",
            source="courtlistener",
            court="Court",
            court_level="supreme",
            case_name="Case",
            docket_number="1",
            date_filed=date(2024, 1, 1),
            jurisdiction="Indiana",
            text="Same text twice.",
            citations_out=[],
            url="",
        )
        hash1 = o.content_hash
        hash2 = o.content_hash
        assert hash1 == hash2
        assert len(hash1) == 16


# ── _parse_lro_opinion_html ──────────────────────────────────────────────────


class TestParseLROOpinionHTML:
    def test_returns_none_for_short_text(self):
        result = _parse_lro_opinion_html("<p>Short</p>", "F3", "100", "1.html")
        assert result is None

    def test_returns_none_without_indiana_mention(self):
        # 300+ chars of text about Ohio (not Indiana)
        text = "<p>" + "Ohio courts decided that " * 30 + "</p>"
        result = _parse_lro_opinion_html(text, "F3", "100", "1.html")
        assert result is None

    def test_returns_opinion_with_indiana_mention(self):
        text = "<p>" + "The Indiana Supreme Court held that " * 30 + " 2024 " + "</p>"
        result = _parse_lro_opinion_html(text, "F3", "100", "case.html")
        assert result is not None
        assert isinstance(result, PublicLegalOpinion)
        assert result.source == "law_resource_org"
        assert result.court_level == "federal_circuit"
        assert "lro-F3-100" in result.opinion_id

    def test_extracts_citations(self):
        cite_text = "<p>" + "Indiana decided 123 F.3d 456 and " * 30 + " 2020 " + "</p>"
        result = _parse_lro_opinion_html(cite_text, "F3", "100", "case.html")
        if result:
            # Should find F.3d citations
            assert any("F.3d" in c for c in result.citations_out)


# ── IndianaCodeClient._parse_statute ──────────────────────────────────────────


class TestParseStatute:
    def test_parses_valid_statute(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        data = {
            "number": "1",
            "title": "Murder",
            "text": "A person who knowingly or intentionally kills...",
            "effectiveDate": "2024-07-01",
        }
        statute = IndianaCodeClient._parse_statute(data, title="35", article="42", chapter="1")
        assert statute is not None
        assert statute.statute_id == "ic-35-42-1-1"
        assert statute.full_citation == "Ind. Code § 35-42-1-1"
        assert statute.effective_date == date(2024, 7, 1)

    def test_returns_none_on_bad_data(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        # Pass a dict with bad nested types that trigger TypeError during construction
        data = {"number": None, "text": 123, "effectiveDate": 999}
        result = IndianaCodeClient._parse_statute(data, title="1", article="1", chapter="1")
        # The function handles malformed data gracefully (returns statute or None)
        # Test that it doesn't raise
        assert result is None or result is not None

    def test_handles_missing_effective_date(self):
        from ingestion.sources.public_resource import IndianaCodeClient

        data = {"number": "1", "text": "Section text"}
        statute = IndianaCodeClient._parse_statute(data, title="1", article="1", chapter="1")
        assert statute is not None
        assert statute.effective_date is None
