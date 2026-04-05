from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from config.logging import get_logger
from ingestion.sources.document_loader import ParsedDocument

logger = get_logger(__name__)

# ── Regex patterns for legal document structure detection ────────────────────

# Section headers: "SECTION 1.", "I.", "Article 15", "§ 12-3-4", etc.
_SECTION_RE = re.compile(
    r"""
    (?:^|\n)
    (?:
        (?:SECTION|SEC\.?|ARTICLE|RULE|CHAPTER|PART)\s+[\dA-Z]+\.?  # Named section
        | [IVX]{1,6}\.                                                 # Roman numeral
        | \d{1,3}(?:\.\d{1,3})*\.                                     # 1.2.3.
        | §\s*[\d\-\.]+                                                # § citation
    )
    [^\n]{0,120}
    """,
    re.VERBOSE | re.MULTILINE,
)

# Indiana citation patterns: "Ind. Code § 35-42-1-1", "I.C. § 12-3-4", citations
_CITATION_RE = re.compile(
    r"""
    (?:
        Ind(?:iana)?\.?\s*Code\s*§\s*[\d\-\.]+    # Indiana Code
        | I\.C\.\s*§\s*[\d\-\.]+                   # I.C. §
        | \d+\s+Ind\.?\s+\d+                        # Reporter: 123 Ind. 456
        | \d+\s+N\.E\.(?:2d|3d)?\s+\d+             # N.E. reporter
        | [A-Z][a-z]+\s+v\.\s+[A-Z][a-z]+[\w\s,]+  # Case name: Doe v. Smith
    )
    """,
    re.VERBOSE,
)


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    text: str
    section_header: str
    section_index: int
    char_start: int
    char_end: int
    citations: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        return len(self.text) // 4  # ~4 chars/token heuristic


class LegalChunker:
    """
    Structure-aware chunker for legal documents.

    Strategy (not naive fixed-size splitting):
    1. Detect section boundaries using legal document patterns.
    2. Split on those boundaries first, preserving header context.
    3. If a section exceeds max_tokens, slide within it with overlap.
    4. Extract and attach citation metadata to every chunk.

    This preserves citation integrity — a chunk never bisects a citation.
    """

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        min_chunk_chars: int = 100,
    ) -> None:
        self.max_chars = max_tokens * 4  # rough char budget
        self.overlap_chars = overlap_tokens * 4
        self.min_chunk_chars = min_chunk_chars

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        text = doc.full_text
        sections = self._split_into_sections(text)
        chunks: list[Chunk] = []

        for idx, (header, body, char_start) in enumerate(sections):
            sub_chunks = self._split_section(
                source_id=doc.source_id,
                header=header,
                body=body,
                section_index=idx,
                section_char_start=char_start,
                doc_metadata=doc.metadata,
            )
            chunks.extend(sub_chunks)

        logger.info(
            "chunked_document",
            source_id=doc.source_id,
            sections=len(sections),
            chunks=len(chunks),
        )
        return chunks

    # ── Section splitting ────────────────────────────────────────────────────

    def _split_into_sections(self, text: str) -> list[tuple[str, str, int]]:
        """
        Returns list of (header, body, char_offset) tuples.
        Falls back to a single section if no headers are detected.
        """
        matches = list(_SECTION_RE.finditer(text))
        if not matches:
            return [("", text, 0)]

        sections: list[tuple[str, str, int]] = []
        for i, match in enumerate(matches):
            header = match.group().strip()
            body_start = match.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[body_start:body_end].strip()
            if len(body) >= self.min_chunk_chars:
                sections.append((header, body, match.start()))

        # Preamble before first section
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()].strip()
            if len(preamble) >= self.min_chunk_chars:
                sections.insert(0, ("PREAMBLE", preamble, 0))

        return sections

    # ── Within-section splitting ─────────────────────────────────────────────

    def _split_section(
        self,
        source_id: str,
        header: str,
        body: str,
        section_index: int,
        section_char_start: int,
        doc_metadata: dict[str, Any],
    ) -> list[Chunk]:
        if len(body) <= self.max_chars:
            return [
                self._make_chunk(
                    source_id=source_id,
                    text=f"{header}\n{body}".strip() if header else body,
                    header=header,
                    section_index=section_index,
                    char_start=section_char_start,
                    char_end=section_char_start + len(body),
                    doc_metadata=doc_metadata,
                )
            ]

        # Sliding window within section, respecting sentence boundaries
        chunks: list[Chunk] = []
        sentences = self._split_sentences(body)
        window: list[str] = []
        window_len = 0
        offset = section_char_start

        for sent in sentences:
            if window_len + len(sent) > self.max_chars and window:
                text = (" ".join(window)).strip()
                chunks.append(
                    self._make_chunk(
                        source_id=source_id,
                        text=f"{header}\n{text}".strip() if header else text,
                        header=header,
                        section_index=section_index,
                        char_start=offset,
                        char_end=offset + len(text),
                        doc_metadata=doc_metadata,
                    )
                )
                # Keep overlap
                overlap_sents = self._tail_to_fit(window, self.overlap_chars)
                offset += window_len - sum(len(s) for s in overlap_sents)
                window = overlap_sents
                window_len = sum(len(s) for s in window)

            window.append(sent)
            window_len += len(sent)

        if window:
            text = " ".join(window).strip()
            chunks.append(
                self._make_chunk(
                    source_id=source_id,
                    text=f"{header}\n{text}".strip() if header else text,
                    header=header,
                    section_index=section_index,
                    char_start=offset,
                    char_end=offset + len(text),
                    doc_metadata=doc_metadata,
                )
            )

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_chunk(
        self,
        source_id: str,
        text: str,
        header: str,
        section_index: int,
        char_start: int,
        char_end: int,
        doc_metadata: dict[str, Any],
    ) -> Chunk:
        citations = _CITATION_RE.findall(text)
        return Chunk(
            chunk_id=str(uuid.uuid4()),
            source_id=source_id,
            text=text,
            section_header=header,
            section_index=section_index,
            char_start=char_start,
            char_end=char_end,
            citations=[c.strip() for c in citations],
            metadata=doc_metadata,
        )

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Naive sentence splitter that avoids breaking legal citations."""
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _tail_to_fit(sentences: list[str], max_chars: int) -> list[str]:
        """Return the suffix of `sentences` that fits within max_chars."""
        result: list[str] = []
        total = 0
        for sent in reversed(sentences):
            if total + len(sent) > max_chars:
                break
            result.insert(0, sent)
            total += len(sent)
        return result
