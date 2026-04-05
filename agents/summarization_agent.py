from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.base_agent import BaseAgent
from generation.bedrock_client import BedrockLLMClient
from generation.prompts.legal_qa import build_summarization_prompt
from ingestion.sources.document_loader import load_from_bytes

logger_name = "agents.summarization"


@dataclass
class SummarizationResult:
    source_id: str
    summary: str
    key_parties: list[str]
    citations: list[str]
    deadlines: list[str]


class SummarizationAgent(BaseAgent):
    """
    Summarizes legal documents (orders, complaints, judgments).

    Input: raw document bytes + metadata
    Output: structured summary with parties, citations, deadlines

    Tool access is intentionally narrow — this agent reads only;
    it has no write or search permissions.
    """

    allowed_tools = ["load_document", "generate_summary"]

    def __init__(self) -> None:
        super().__init__()
        self._llm = BedrockLLMClient()

    async def _execute(self, **kwargs: Any) -> SummarizationResult:
        source_id: str = kwargs["source_id"]
        content: bytes = kwargs["content"]
        filename: str = kwargs.get("filename", "document.pdf")
        metadata: dict[str, Any] = kwargs.get("metadata", {})
        doc_type: str = kwargs.get("doc_type", "legal document")

        # Tool: load document
        self._record_tool_call("load_document", {"source_id": source_id, "filename": filename})
        doc = load_from_bytes(
            content=content, source_id=source_id, filename=filename, metadata=metadata
        )

        # Tool: generate summary
        self._record_tool_call("generate_summary", {"source_id": source_id, "doc_type": doc_type})

        import asyncio

        prompt = build_summarization_prompt(doc.full_text, doc_type)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: self._llm.complete(
                system=(
                    "You are a precise legal document analyst. "
                    "Extract structured information only."
                ),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            ),
        )

        return SummarizationResult(
            source_id=source_id,
            summary=raw,
            key_parties=_extract_parties(raw),
            citations=_extract_citations(raw),
            deadlines=_extract_deadlines(raw),
        )


def _extract_parties(text: str) -> list[str]:
    import re

    matches = re.findall(
        r"(?:Plaintiff|Defendant|Petitioner|Respondent)[:\s]+([A-Z][A-Za-z\s,\.]+)", text
    )
    return [m.strip() for m in matches]


def _extract_citations(text: str) -> list[str]:
    import re

    return re.findall(r"Ind(?:iana)?\.?\s*Code\s*§\s*[\d\-\.]+|I\.C\.\s*§\s*[\d\-\.]+", text)


def _extract_deadlines(text: str) -> list[str]:
    import re

    return re.findall(
        r"\b(?:within \d+ days?|by [A-Z][a-z]+ \d{1,2},?\s*\d{4}|deadline[:\s]+[^\n\.]+)\b",
        text,
        re.IGNORECASE,
    )
