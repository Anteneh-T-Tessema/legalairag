from __future__ import annotations

from retrieval.hybrid_search import SearchResult


def build_legal_qa_system_prompt(jurisdiction: str | None = None) -> str:
    scope = f"Indiana ({jurisdiction})" if jurisdiction else "Indiana"
    return f"""You are a legal research assistant for {scope} courts.

RULES (non-negotiable):
1. Every factual claim you make MUST be grounded in the provided context chunks.
2. Cite the source of every claim using the format [SOURCE: <source_id>, §<section>].
3. If the context does not support an answer, respond:
   "The provided documents do not contain sufficient information to answer this question."
4. Never speculate or extrapolate beyond what the sources state.
5. State the jurisdiction and date of any statute or ruling you reference.
6. Use plain language understandable to non-lawyers while preserving legal precision.
7. Do not provide legal advice — state findings only."""


def build_legal_qa_user_prompt(
    query: str,
    context_chunks: list[SearchResult],
) -> str:
    context_block = _format_context(context_chunks)
    return f"""QUESTION: {query}

CONTEXT (retrieved legal documents):
{context_block}

Provide a concise, citation-backed answer using only the context above."""


def build_summarization_prompt(document_text: str, doc_type: str = "legal document") -> str:
    return f"""Summarize the following {doc_type}.

Requirements:
- 3–5 sentence executive summary
- List key parties, dates, and jurisdictions
- List every statutory citation mentioned (e.g. Ind. Code §)
- Flag any deadlines, obligations, or conditions precedent

DOCUMENT:
{document_text[:8000]}"""


def build_case_research_prompt(query: str, context_chunks: list[SearchResult]) -> str:
    context_block = _format_context(context_chunks)
    return f"""You are conducting legal case research.

RESEARCH QUESTION: {query}

RELEVANT CASES AND STATUTES:
{context_block}

Provide:
1. A direct answer to the research question
2. The controlling authority (statute, case)
3. Any exceptions or qualifications
4. Confidence level: High / Medium / Low (based on evidence quality)

Cite all sources with [SOURCE: <source_id>]."""


def _format_context(chunks: list[SearchResult]) -> str:
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        citations_str = ", ".join(chunk.citations) if chunk.citations else "none"
        parts.append(
            f"[{i}] SOURCE: {chunk.source_id} | SECTION: {chunk.section}\n"
            f"Citations: {citations_str}\n"
            f"{chunk.content}\n"
        )
    return "\n---\n".join(parts)
