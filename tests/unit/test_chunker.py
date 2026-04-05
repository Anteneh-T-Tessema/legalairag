from __future__ import annotations

from ingestion.pipeline.chunker import Chunk, LegalChunker
from ingestion.sources.document_loader import ParsedDocument


def _make_doc(text: str) -> ParsedDocument:
    return ParsedDocument(
        source_id="test-001",
        filename="test.txt",
        mime_type="text/plain",
        raw_text=text,
        pages=[text],
        metadata={},
    )


class TestLegalChunker:
    def setup_method(self) -> None:
        self.chunker = LegalChunker(max_tokens=100, overlap_tokens=10)

    def test_short_doc_produces_single_chunk(self) -> None:
        doc = _make_doc("This is a short document with no sections.")
        chunks = self.chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0].source_id == "test-001"

    def test_chunk_ids_are_unique(self) -> None:
        doc = _make_doc("A " * 600)  # force multi-chunk
        chunks = self.chunker.chunk(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_section_header_detected(self) -> None:
        body1 = (
            "The court shall have jurisdiction over all matters arising under this chapter. " * 3
        )
        body2 = (
            "Any person who violates the provisions of this "
            "section shall be guilty of a Class A misdemeanor. " * 3
        )
        text = f"SECTION 1. General Provisions\n{body1}\n\nSECTION 2. Penalties\n{body2}"
        doc = _make_doc(text)
        chunks = self.chunker.chunk(doc)
        headers = [c.section_header for c in chunks]
        assert any("SECTION 1" in h for h in headers)
        assert any("SECTION 2" in h for h in headers)

    def test_indiana_citations_extracted(self) -> None:
        text = "Under Ind. Code § 35-42-1-1, murder is a Level 1 felony."
        doc = _make_doc(text)
        chunks = self.chunker.chunk(doc)
        all_citations = [c for chunk in chunks for c in chunk.citations]
        assert any("35-42-1-1" in cite for cite in all_citations)

    def test_no_empty_chunks(self) -> None:
        doc = _make_doc("SECTION 1.\n\nSECTION 2.\nSome content here that is long enough.")
        chunks = self.chunker.chunk(doc)
        for chunk in chunks:
            assert len(chunk.text.strip()) > 0

    def test_chunk_preserves_source_id(self) -> None:
        doc = _make_doc("Content " * 200)
        chunks = self.chunker.chunk(doc)
        for chunk in chunks:
            assert chunk.source_id == "test-001"

    # ── token_estimate property ───────────────────────────────────────────────

    def test_chunk_token_estimate(self) -> None:
        """Cover line 59: token_estimate = len(text) // 4."""
        chunk = Chunk(
            chunk_id="c1",
            source_id="s1",
            text="hello world",
            section_header="",
            section_index=0,
            char_start=0,
            char_end=11,
            citations=[],
            metadata={},
        )
        assert chunk.token_estimate == len("hello world") // 4

    # ── Preamble before first section ─────────────────────────────────────────

    def test_preamble_before_first_section_included(self) -> None:
        """Cover lines 131-133: text before the first section becomes PREAMBLE chunk."""
        preamble = "This is introductory preamble text that is definitely long enough. " * 3
        body = "The main section body content with legal provisions. " * 3
        text = f"{preamble}\n\nSECTION 1. Main Content\n{body}"
        doc = _make_doc(text)
        chunks = self.chunker.chunk(doc)
        headers = [c.section_header for c in chunks]
        assert "PREAMBLE" in headers

    # ── Window overflow (long section splits) ────────────────────────────────

    def test_large_section_body_splits_into_multiple_chunks(self) -> None:
        """Cover lines 170-186: section body exceeds max_chars → window flush with overlap."""
        # max_tokens=100 → max_chars=400; 20 sentences × ~50 chars each = ~1000 chars
        sentence = "A legal provision establishes the following requirement. "
        body = sentence * 20
        text = f"SECTION 1. Long Section\n{body}"
        doc = _make_doc(text)
        chunks = self.chunker.chunk(doc)
        assert len(chunks) > 1

    def test_tail_to_fit_returns_suffix_within_limit(self) -> None:
        """Cover lines 241-248: _tail_to_fit returns suffix fitting max_chars."""
        chunker = LegalChunker()
        sentences = [
            "Short sentence one.",
            "Medium length sentence two here.",
            "Another medium sentence three.",
            "Final sentence four.",
        ]
        result = chunker._tail_to_fit(sentences, max_chars=60)
        total = sum(len(s) for s in result)
        assert total <= 60
        # Must be a suffix (preserves order)
        if result:
            n = len(result)
            assert result == sentences[-n:]

    def test_tail_to_fit_empty_when_single_sentence_too_long(self) -> None:
        """_tail_to_fit returns [] when even the last sentence is too long."""
        chunker = LegalChunker()
        sentences = ["This sentence is considerably longer than ten characters."]
        result = chunker._tail_to_fit(sentences, max_chars=5)
        assert result == []

    def test_tail_to_fit_all_sentences_fit(self) -> None:
        """Cover 243->248: for loop completes without break when all sentences fit."""
        chunker = LegalChunker()
        sentences = ["Hi.", "Ok.", "Yes."]
        result = chunker._tail_to_fit(sentences, max_chars=1000)
        assert result == sentences  # all fit, returned in order

    def test_preamble_too_short_is_excluded(self) -> None:
        """Cover 132->135: preamble shorter than min_chunk_chars is not added."""
        # min_chunk_chars=100; preamble is just 5 chars
        short_preamble = "Hi.\n\n"
        body = "The court holds jurisdiction per statute. " * 4
        text = f"{short_preamble}SECTION 1. Main\n{body}"
        doc = _make_doc(text)
        chunks = self.chunker.chunk(doc)
        headers = [c.section_header for c in chunks]
        assert "PREAMBLE" not in headers

    def test_split_section_empty_window_returns_no_chunks(self) -> None:
        """Cover 191->205 False branch: window is empty after the for loop."""
        # max_tokens=1 → max_chars=4; body of 5 spaces exceeds max_chars
        # but _split_sentences returns [] for whitespace-only text → window stays empty
        chunker = LegalChunker(max_tokens=1)
        result = chunker._split_section(
            source_id="s1",
            header="",
            body="     ",  # 5 spaces: len=5 > max_chars=4, but no real sentences
            section_index=0,
            section_char_start=0,
            doc_metadata={},
        )
        assert result == []
