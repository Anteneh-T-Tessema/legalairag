"""Unit tests for generation.prompts.legal_qa — prompt builders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from generation.prompts.legal_qa import (
    _format_context,
    build_case_research_prompt,
    build_legal_qa_system_prompt,
    build_legal_qa_user_prompt,
    build_summarization_prompt,
)


@dataclass
class _FakeSearchResult:
    chunk_id: str = "c1"
    source_id: str = "src-1"
    content: str = "Indiana Code § 35-42-1-1 defines murder."
    section: str = "§35-42-1-1"
    citations: list[str] = field(default_factory=lambda: ["Ind. Code § 35-42-1-1"])
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.5


class TestBuildLegalQASystemPrompt:
    def test_includes_indiana(self):
        prompt = build_legal_qa_system_prompt()
        assert "Indiana" in prompt

    def test_includes_jurisdiction(self):
        prompt = build_legal_qa_system_prompt("Marion County")
        assert "Marion County" in prompt

    def test_contains_citation_rule(self):
        prompt = build_legal_qa_system_prompt()
        assert "SOURCE" in prompt

    def test_contains_no_legal_advice_rule(self):
        prompt = build_legal_qa_system_prompt()
        assert "legal advice" in prompt.lower()


class TestBuildLegalQAUserPrompt:
    def test_includes_query(self):
        chunks = [_FakeSearchResult()]
        prompt = build_legal_qa_user_prompt("What is murder?", chunks)
        assert "What is murder?" in prompt

    def test_includes_context_content(self):
        chunks = [_FakeSearchResult(content="Murder is defined under...")]
        prompt = build_legal_qa_user_prompt("q", chunks)
        assert "Murder is defined under..." in prompt

    def test_includes_source_id(self):
        chunks = [_FakeSearchResult(source_id="doc-42")]
        prompt = build_legal_qa_user_prompt("q", chunks)
        assert "doc-42" in prompt


class TestBuildSummarizationPrompt:
    def test_includes_doc_type(self):
        prompt = build_summarization_prompt("Full text here", "court order")
        assert "court order" in prompt

    def test_truncates_long_text(self):
        long_text = "x" * 20000
        prompt = build_summarization_prompt(long_text)
        # Should include up to 8000 chars of input
        assert len(prompt) < 20000

    def test_default_doc_type(self):
        prompt = build_summarization_prompt("Text")
        assert "legal document" in prompt

    def test_mentions_statutory_citations(self):
        prompt = build_summarization_prompt("Text")
        assert "citation" in prompt.lower()


class TestBuildCaseResearchPrompt:
    def test_includes_research_question(self):
        chunks = [_FakeSearchResult()]
        prompt = build_case_research_prompt("Is self-defense valid?", chunks)
        assert "Is self-defense valid?" in prompt

    def test_includes_confidence_request(self):
        chunks = [_FakeSearchResult()]
        prompt = build_case_research_prompt("q", chunks)
        assert "Confidence" in prompt

    def test_includes_context(self):
        chunks = [_FakeSearchResult(content="Relevant statutes...")]
        prompt = build_case_research_prompt("q", chunks)
        assert "Relevant statutes..." in prompt


class TestFormatContext:
    def test_formats_single_chunk(self):
        chunks = [_FakeSearchResult(source_id="doc-1", section="§1", content="Text")]
        output = _format_context(chunks)
        assert "SOURCE: doc-1" in output
        assert "SECTION: §1" in output
        assert "Text" in output

    def test_formats_multiple_chunks_with_separator(self):
        chunks = [_FakeSearchResult(source_id="a"), _FakeSearchResult(source_id="b")]
        output = _format_context(chunks)
        assert "---" in output
        assert "SOURCE: a" in output
        assert "SOURCE: b" in output

    def test_empty_citations_shows_none(self):
        chunks = [_FakeSearchResult(citations=[])]
        output = _format_context(chunks)
        assert "Citations: none" in output

    def test_multiple_citations(self):
        chunks = [_FakeSearchResult(citations=["Cite A", "Cite B"])]
        output = _format_context(chunks)
        assert "Cite A" in output
        assert "Cite B" in output
