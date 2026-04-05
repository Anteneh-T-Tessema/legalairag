"""Unit tests for agents.summarization_agent — SummarizationAgent + helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from agents.summarization_agent import (
    SummarizationAgent,
    SummarizationResult,
    _extract_citations,
    _extract_deadlines,
    _extract_parties,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _extract_parties ──────────────────────────────────────────────────────────


class TestExtractParties:
    def test_basic_extraction(self):
        text = "Plaintiff: John Smith; Defendant: Jane Doe"
        parties = _extract_parties(text)
        assert "John Smith" in parties
        assert "Jane Doe" in parties

    def test_petitioner_respondent(self):
        text = "Petitioner: Alice Johnson; Respondent: Bob Williams"
        parties = _extract_parties(text)
        assert len(parties) == 2

    def test_no_parties(self):
        text = "No relevant parties mentioned in this document."
        assert _extract_parties(text) == []


# ── _extract_citations ────────────────────────────────────────────────────────


class TestExtractCitations:
    def test_standard_indiana_code(self):
        text = "Under Ind. Code § 35-42-1-1, murder is defined..."
        cites = _extract_citations(text)
        assert len(cites) >= 1
        assert any("35-42-1-1" in c for c in cites)

    def test_abbreviated_ic(self):
        text = "Pursuant to I.C. § 12-7-2-38.1, the definition..."
        cites = _extract_citations(text)
        assert len(cites) >= 1

    def test_indiana_code_without_period(self):
        text = "Indiana Code § 31-14-13-6 governs custody."
        cites = _extract_citations(text)
        assert len(cites) >= 1

    def test_no_citations(self):
        text = "General legal commentary without specific statutes."
        assert _extract_citations(text) == []


# ── _extract_deadlines ────────────────────────────────────────────────────────


class TestExtractDeadlines:
    def test_within_days(self):
        text = "Must respond within 20 days of service."
        deadlines = _extract_deadlines(text)
        assert len(deadlines) >= 1

    def test_specific_date(self):
        text = "All motions must be filed by January 15, 2025."
        deadlines = _extract_deadlines(text)
        assert len(deadlines) >= 1

    def test_deadline_label(self):
        text = "Deadline: File by end of discovery period"
        deadlines = _extract_deadlines(text)
        assert len(deadlines) >= 1

    def test_no_deadlines(self):
        text = "The court finds in favour of the plaintiff."
        assert _extract_deadlines(text) == []


# ── SummarizationAgent._execute ──────────────────────────────────────────


class TestSummarizationAgent:
    _DEFAULT_LLM = "Summary.\nPlaintiff: Alice\nInd. Code § 1-2-3\nwithin 30 days"

    def _make_agent(self, llm_output: str = _DEFAULT_LLM):
        with patch("agents.summarization_agent.BedrockLLMClient") as MockLLM:
            MockLLM.return_value.complete = MagicMock(return_value=llm_output)
            agent = SummarizationAgent()
            return agent

    def test_execute_returns_summarization_result(self):
        llm_text = (
            "Summary of the order.\n"
            "Plaintiff: Alice Brown\n"
            "Ind. Code § 35-42-1-1\n"
            "within 30 days of filing"
        )
        with (
            patch("agents.summarization_agent.BedrockLLMClient") as MockLLM,
            patch("agents.summarization_agent.load_from_bytes") as mock_load,
        ):
            MockLLM.return_value.complete = MagicMock(return_value=llm_text)
            mock_load.return_value = MagicMock(full_text="Full document text here...")

            agent = SummarizationAgent()
            result = _run(
                agent.run(
                    source_id="doc-1",
                    content=b"fake pdf bytes",
                    filename="order.pdf",
                )
            )

            assert isinstance(result, SummarizationResult)
            assert result.source_id == "doc-1"
            assert result.summary == llm_text

    def test_execute_extracts_parties(self):
        llm_text = "Defendant: John Doe"
        with (
            patch("agents.summarization_agent.BedrockLLMClient") as MockLLM,
            patch("agents.summarization_agent.load_from_bytes") as mock_load,
        ):
            MockLLM.return_value.complete = MagicMock(return_value=llm_text)
            mock_load.return_value = MagicMock(full_text="text")

            agent = SummarizationAgent()
            result = _run(agent.run(source_id="doc-2", content=b"data"))
            assert "John Doe" in result.key_parties

    def test_execute_extracts_citations(self):
        llm_text = "Under Ind. Code § 35-42-1-1, the defendant is guilty."
        with (
            patch("agents.summarization_agent.BedrockLLMClient") as MockLLM,
            patch("agents.summarization_agent.load_from_bytes") as mock_load,
        ):
            MockLLM.return_value.complete = MagicMock(return_value=llm_text)
            mock_load.return_value = MagicMock(full_text="text")

            agent = SummarizationAgent()
            result = _run(agent.run(source_id="doc-3", content=b"data"))
            assert len(result.citations) >= 1

    def test_allowed_tools_are_narrow(self):
        assert SummarizationAgent.allowed_tools == ["load_document", "generate_summary"]
        assert "search" not in SummarizationAgent.allowed_tools
