from __future__ import annotations

from ingestion.pipeline.chunker import LegalChunker
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
