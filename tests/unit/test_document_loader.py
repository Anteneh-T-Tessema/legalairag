"""Unit tests for ingestion.sources.document_loader — load_from_bytes + parsers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ingestion.sources.document_loader import (
    ParsedDocument,
    _normalize_whitespace,
    load_from_bytes,
)

# ── _normalize_whitespace ─────────────────────────────────────────────────────


class TestNormalizeWhitespace:
    def test_collapses_multiple_newlines(self):
        assert _normalize_whitespace("a\n\n\n\nb") == "a\n\nb"

    def test_collapses_spaces_and_tabs(self):
        assert _normalize_whitespace("a   b\t\tc") == "a b c"

    def test_strips_leading_trailing(self):
        assert _normalize_whitespace("   hello   ") == "hello"

    def test_empty_string(self):
        assert _normalize_whitespace("") == ""


# ── load_from_bytes — plaintext ───────────────────────────────────────────────


class TestLoadPlaintext:
    def test_parses_txt(self):
        content = b"Hello, this is a legal document."
        doc = load_from_bytes(content, source_id="doc-1", filename="brief.txt")
        assert isinstance(doc, ParsedDocument)
        assert doc.source_id == "doc-1"
        assert doc.mime_type == "text/plain"
        assert doc.raw_text == "Hello, this is a legal document."
        assert doc.pages == ["Hello, this is a legal document."]

    def test_parses_text_extension(self):
        doc = load_from_bytes(b"data", source_id="d", filename="file.text")
        assert doc.mime_type == "text/plain"

    def test_preserves_metadata(self):
        meta = {"court": "Marion County"}
        doc = load_from_bytes(b"text", source_id="d", filename="f.txt", metadata=meta)
        assert doc.metadata["court"] == "Marion County"

    def test_full_text_property(self):
        doc = load_from_bytes(b"hello world", source_id="x", filename="a.txt")
        assert doc.full_text == "hello world"


# ── load_from_bytes — HTML ────────────────────────────────────────────────────


class TestLoadHTML:
    def test_parses_html(self):
        html = b"<html><body><p>Indiana Code.</p><script>evil();</script></body></html>"
        with patch("bs4.BeautifulSoup") as MockSoup:
            mock_soup = MagicMock()
            MockSoup.return_value = mock_soup
            mock_soup.return_value = []
            mock_soup.__call__ = MagicMock(return_value=[])
            mock_soup.get_text.return_value = "Indiana Code."
            doc = load_from_bytes(html, source_id="h", filename="page.html")
            assert doc.mime_type == "text/html"

    def test_htm_extension(self):
        with patch("bs4.BeautifulSoup") as MockSoup:
            mock_soup = MagicMock()
            MockSoup.return_value = mock_soup
            mock_soup.__call__ = MagicMock(return_value=[])
            mock_soup.get_text.return_value = "text"
            doc = load_from_bytes(b"<p>hi</p>", source_id="h", filename="page.htm")
            assert doc.mime_type == "text/html"


# ── load_from_bytes — PDF ─────────────────────────────────────────────────────


class TestLoadPDF:
    def test_parses_pdf_by_extension(self):
        with patch("ingestion.sources.document_loader.pdfplumber") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Page 1 text"
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.pages = [mock_page]
            mock_pdf.open.return_value = mock_ctx

            doc = load_from_bytes(b"fake", source_id="p", filename="order.pdf")
            assert doc.mime_type == "application/pdf"
            assert doc.pages == ["Page 1 text"]

    def test_parses_pdf_by_magic_bytes(self):
        with patch("ingestion.sources.document_loader.pdfplumber") as mock_pdf:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Content"
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.pages = [mock_page]
            mock_pdf.open.return_value = mock_ctx

            doc = load_from_bytes(b"%PDF-1.4...", source_id="p", filename="noext")
            assert doc.mime_type == "application/pdf"


# ── load_from_bytes — DOCX ────────────────────────────────────────────────────


class TestLoadDocx:
    def test_parses_docx(self):
        mock_para = MagicMock()
        mock_para.text = "Paragraph one"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_doc
        with patch.dict("sys.modules", {"docx": mock_docx_module}):
            doc = load_from_bytes(b"docx-bytes", source_id="d", filename="brief.docx")
            assert doc.mime_type.startswith("application/vnd.openxmlformats")


# ── load_from_bytes — unsupported ─────────────────────────────────────────────


class TestLoadUnsupported:
    def test_falls_back_to_plaintext(self):
        content = b"Unknown format data"
        doc = load_from_bytes(content, source_id="u", filename="data.xyz")
        assert doc.mime_type == "text/plain"
        assert doc.raw_text == "Unknown format data"

    def test_handles_binary_content_gracefully(self):
        content = b"\x00\x01\x02\x03"
        doc = load_from_bytes(content, source_id="b", filename="binary.dat")
        assert doc.mime_type == "text/plain"
        # Should not raise — uses errors="replace"
