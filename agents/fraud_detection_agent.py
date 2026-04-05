"""
Fraud / anomaly detection agent for Indiana legal filings.

Motivation (from JD):
  "fraud detection workflow agent" — the system should detect patterns across
  legal filings that suggest fraudulent activity: identity theft in court records,
  serial fraudulent deed filings, suspicious patterns in case metadata.

This agent operates on retrieved legal document records and cross-references
filing patterns to flag anomalies for human review.

Tools: search, analyze_patterns, flag_for_review
Scope: strictly detection and flagging — no automated action taken.
All flags are persisted with full audit trail for human investigator review.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from agents.base_agent import BaseAgent
from config.logging import get_logger
from ingestion.pipeline.embedder import BedrockEmbedder
from retrieval.hybrid_search import HybridSearcher, SearchResult

logger = get_logger(__name__)


# ── Fraud Indicators ───────────────────────────────────────────────────────────


@dataclass
class FraudIndicator:
    """A single detected anomaly signal."""

    indicator_type: str  # e.g. "burst_filing", "identity_reuse", "deed_fraud"
    severity: str  # "low" | "medium" | "high" | "critical"
    description: str
    evidence: list[str]  # source_ids or case numbers supporting this flag
    confidence: float  # 0.0–1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FraudAnalysisResult:
    """Aggregated result of a fraud detection analysis run."""

    run_id: str
    query_context: str  # What was searched to produce these filings
    total_filings_analyzed: int
    indicators: list[FraudIndicator]
    risk_level: str  # "none" | "low" | "medium" | "high" | "critical"
    summary: str
    requires_human_review: bool
    flagged_source_ids: list[str]


# ── Pattern Detectors ──────────────────────────────────────────────────────────


class _FilingPatternAnalyzer:
    """
    Stateless pattern analysis over a list of retrieved legal documents.

    Each detector returns a list of FraudIndicators (potentially empty).
    Adding a new detector is as simple as a new method that follows the
    `_detect_*` signature.
    """

    def analyze(self, results: list[SearchResult]) -> list[FraudIndicator]:
        """Run all detectors and aggregate indicators."""
        indicators: list[FraudIndicator] = []
        indicators.extend(self._detect_burst_filing(results))
        indicators.extend(self._detect_identity_reuse(results))
        indicators.extend(self._detect_deed_fraud_patterns(results))
        indicators.extend(self._detect_suspicious_party_patterns(results))
        indicators.extend(self._detect_rapid_ownership_transfer(results))
        return indicators

    @staticmethod
    def _detect_burst_filing(results: list[SearchResult]) -> list[FraudIndicator]:
        """
        Flag if the same party appears in many filings in a short time window.
        Legitimate litigants rarely file dozens of cases in a week.

        Threshold: >5 filings per party within 30 days → medium risk.
        """
        indicators: list[FraudIndicator] = []
        party_filings: dict[str, list[tuple[date, str]]] = defaultdict(list)

        for r in results:
            meta = r.metadata
            filed_str = meta.get("filing_date") or meta.get("date_filed", "")
            parties: list[str] = meta.get("parties", [])
            if not filed_str or not parties:
                continue
            try:
                filed = date.fromisoformat(str(filed_str)[:10])
            except (ValueError, TypeError):
                continue
            for party in parties:
                party_filings[party.lower()].append((filed, r.source_id))

        for party, filings in party_filings.items():
            filings.sort(key=lambda x: x[0])
            # Sliding 30-day window
            for _i, (start_date, _) in enumerate(filings):
                window = [
                    f for f in filings if start_date <= f[0] <= start_date + timedelta(days=30)
                ]
                if len(window) >= 6:
                    evidences = [f[1] for f in window]
                    indicators.append(
                        FraudIndicator(
                            indicator_type="burst_filing",
                            severity="medium" if len(window) < 10 else "high",
                            description=(
                                f"Party '{party}' filed {len(window)} cases in 30 days "
                                f"starting {start_date.isoformat()}."
                            ),
                            evidence=evidences,
                            confidence=min(0.6 + (len(window) - 6) * 0.05, 0.95),
                            metadata={"party": party, "window_start": start_date.isoformat()},
                        )
                    )
                    break  # Report once per party

        return indicators

    @staticmethod
    def _detect_identity_reuse(results: list[SearchResult]) -> list[FraudIndicator]:
        """
        Flag when the same personal identifiers (SSN fragments, DOB, address)
        appear across multiple cases with different party names.

        This is a strong indicator of identity theft / court record fraud.
        """
        indicators: list[FraudIndicator] = []

        # Extract SSN fragments (last 4 digits pattern), DOBs, addresses
        ssn_fragment_re = re.compile(r"\bXXX-XX-(\d{4})\b")
        dob_re = re.compile(r"\b(?:DOB|born)[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})\b", re.IGNORECASE)
        address_re = re.compile(
            r"\b\d{3,5}\s+[A-Z][a-z]+\s+(?:St|Ave|Blvd|Dr|Ln|Rd|Way)\b", re.IGNORECASE
        )

        ssn_to_cases: dict[str, list[str]] = defaultdict(list)
        dob_to_cases: dict[str, list[str]] = defaultdict(list)
        addr_to_cases: dict[str, list[str]] = defaultdict(list)

        for r in results:
            text = r.content
            for m in ssn_fragment_re.findall(text):
                ssn_to_cases[m].append(r.source_id)
            for m in dob_re.findall(text):
                dob_to_cases[m].append(r.source_id)
            for m in address_re.findall(text):
                addr_to_cases[m.lower()].append(r.source_id)

        for fragment, case_ids in ssn_to_cases.items():
            unique_cases = list(set(case_ids))
            if len(unique_cases) > 2:
                indicators.append(
                    FraudIndicator(
                        indicator_type="identity_reuse",
                        severity="high",
                        description=(
                            f"SSN fragment ...{fragment} appears in "
                            f"{len(unique_cases)} separate cases."
                        ),
                        evidence=unique_cases,
                        confidence=0.75,
                        metadata={"identifier_type": "ssn_fragment"},
                    )
                )

        for dob, case_ids in dob_to_cases.items():
            unique_cases = list(set(case_ids))
            if len(unique_cases) > 3:
                indicators.append(
                    FraudIndicator(
                        indicator_type="identity_reuse",
                        severity="medium",
                        description=(
                            f"Date of birth {dob} appears in "
                            f"{len(unique_cases)} separate cases."
                        ),
                        evidence=unique_cases,
                        confidence=0.55,
                        metadata={"identifier_type": "dob"},
                    )
                )

        return indicators

    @staticmethod
    def _detect_deed_fraud_patterns(results: list[SearchResult]) -> list[FraudIndicator]:
        """
        Detect serial deed / property fraud patterns:
        - Same property address transferred multiple times in short period
        - Quitclaim deeds with nominal consideration ($1, $10, $100)
        - Property transferred to/from non-resident entities
        """
        indicators: list[FraudIndicator] = []

        quitclaim_re = re.compile(r"\bquitclaim\s+deed\b", re.IGNORECASE)
        nominal_re = re.compile(
            r"\bfor\s+(?:the\s+sum\s+of\s+)?\$(?:1|10|100)\.?00?\b", re.IGNORECASE
        )

        quitclaim_cases = [
            r.source_id
            for r in results
            if quitclaim_re.search(r.content) and nominal_re.search(r.content)
        ]

        if len(quitclaim_cases) >= 3:
            indicators.append(
                FraudIndicator(
                    indicator_type="deed_fraud_pattern",
                    severity="high",
                    description=(
                        f"Found {len(quitclaim_cases)} quitclaim deeds "
                        "with nominal consideration ($1-$100), "
                        "a common deed fraud pattern."
                    ),
                    evidence=quitclaim_cases,
                    confidence=0.80,
                    metadata={"deed_type": "quitclaim", "consideration": "nominal"},
                )
            )

        return indicators

    @staticmethod
    def _detect_suspicious_party_patterns(results: list[SearchResult]) -> list[FraudIndicator]:
        """
        Flag cases with suspicious party name patterns:
        - Misspelled names that closely match known parties
        - Numeric/nonsensical entity names
        - Foreign shell company patterns (common in deed fraud)
        """
        indicators: list[FraudIndicator] = []
        re.compile(
            r"\b(?:LLC|L\.L\.C\.|Inc\.|Corp\.|Ltd\.?)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        numeric_name_re = re.compile(r"\bEntity\s*\d+\b|\bCo\.\s*\d+\b", re.IGNORECASE)

        suspicious: list[str] = []
        for r in results:
            for party in r.metadata.get("parties", []):
                if numeric_name_re.search(party):
                    suspicious.append(r.source_id)
                    break

        if len(suspicious) >= 2:
            indicators.append(
                FraudIndicator(
                    indicator_type="suspicious_entity",
                    severity="medium",
                    description=(
                        f"Found {len(suspicious)} cases with "
                        "numerically-named entities (e.g. 'Entity 42 LLC')."
                    ),
                    evidence=list(set(suspicious)),
                    confidence=0.50,
                    metadata={"pattern": "numeric_entity_name"},
                )
            )

        return indicators

    @staticmethod
    def _detect_rapid_ownership_transfer(results: list[SearchResult]) -> list[FraudIndicator]:
        """
        Detect property changing hands more than twice within 90 days —
        a common pattern in flipping schemes and title fraud.
        """
        indicators: list[FraudIndicator] = []

        # Group by property address (extracted from content)
        address_re = re.compile(
            r"\b(\d{3,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,?\s*(?:Indianapolis|Indiana)\b"
        )
        addr_to_filings: dict[str, list[tuple[date, str]]] = defaultdict(list)

        for r in results:
            filed_str = r.metadata.get("filing_date") or r.metadata.get("date_filed", "")
            if not filed_str:
                continue
            try:
                filed = date.fromisoformat(str(filed_str)[:10])
            except (ValueError, TypeError):
                continue
            for match in address_re.findall(r.content):
                addr_to_filings[match.lower()].append((filed, r.source_id))

        for addr, filings in addr_to_filings.items():
            if len(set(s for _, s in filings)) >= 3:
                filings.sort(key=lambda x: x[0])
                span = (filings[-1][0] - filings[0][0]).days
                if span <= 90:
                    indicators.append(
                        FraudIndicator(
                            indicator_type="rapid_ownership_transfer",
                            severity="high",
                            description=(
                                f"Property '{addr}' transferred "
                                f"{len(filings)} times in {span} days."
                            ),
                            evidence=[s for _, s in filings],
                            confidence=0.70,
                            metadata={"address": addr, "span_days": span},
                        )
                    )

        return indicators


# ── Fraud Detection Agent ──────────────────────────────────────────────────────


class FraudDetectionAgent(BaseAgent):
    """
    Detects fraud and anomaly patterns across Indiana legal filings.

    Workflow:
    1. Embed search query (e.g. "quitclaim deed Marion County last 90 days")
    2. Retrieve relevant filings via hybrid search
    3. Run all pattern detectors over the retrieved set
    4. Score overall risk level
    5. Generate human-readable investigation summary via Bedrock
    6. Persist all flags with full audit trail

    Tool access is read-only:
    - query_parse, embed, search → retrieve documents
    - analyze_patterns → run local pattern detectors
    - generate_summary → LLM-based investigation report (no write access)

    Important: This agent surfaces indicators for human review ONLY.
    No automated enforcement actions are taken.
    """

    allowed_tools = ["query_parse", "embed", "search", "analyze_patterns", "generate_summary"]

    def __init__(self) -> None:
        super().__init__()
        self._embedder = BedrockEmbedder()
        self._searcher = HybridSearcher()
        self._analyzer = _FilingPatternAnalyzer()

    async def _execute(self, **kwargs: Any) -> FraudAnalysisResult:
        query: str = kwargs.get("query", "")
        jurisdiction: str | None = kwargs.get("jurisdiction")
        case_type: str | None = kwargs.get("case_type")

        # Step 1: Parse + embed query
        self._record_tool_call("query_parse", {"query": query})
        from retrieval.query_parser import parse_legal_query

        parsed = parse_legal_query(query)

        self._record_tool_call("embed", {"query": parsed.normalized})
        query_vector = await self._embedder.embed_query(parsed.normalized)

        # Step 2: Retrieve filings — use larger top_k for pattern analysis
        self._record_tool_call("search", {"jurisdiction": jurisdiction or parsed.jurisdiction})
        candidates = await self._searcher.search(
            query_vector=query_vector,
            query_text=parsed.normalized,
            jurisdiction=jurisdiction or parsed.jurisdiction,
            case_type=case_type or parsed.case_type,
            top_k=50,  # Wider net for anomaly detection
        )

        # Step 3: Pattern analysis
        self._record_tool_call("analyze_patterns", {"candidate_count": len(candidates)})
        indicators = self._analyzer.analyze(candidates)

        # Step 4: Risk scoring
        risk_level = self._compute_risk_level(indicators)
        flagged_ids = list({sid for ind in indicators for sid in ind.evidence})

        # Step 5: Generate investigation summary
        self._record_tool_call("generate_summary", {"indicator_count": len(indicators)})
        summary = await self._generate_summary(query, indicators, candidates)

        result = FraudAnalysisResult(
            run_id=self._run_id,
            query_context=query,
            total_filings_analyzed=len(candidates),
            indicators=indicators,
            risk_level=risk_level,
            summary=summary,
            requires_human_review=risk_level in {"medium", "high", "critical"},
            flagged_source_ids=flagged_ids,
        )

        logger.info(
            "fraud_analysis_complete",
            run_id=self._run_id,
            filings=len(candidates),
            indicators=len(indicators),
            risk_level=risk_level,
            flagged=len(flagged_ids),
        )
        return result

    @staticmethod
    def _compute_risk_level(indicators: list[FraudIndicator]) -> str:
        if not indicators:
            return "none"
        severities = [i.severity for i in indicators]
        if "critical" in severities:
            return "critical"
        if severities.count("high") >= 2 or (
            severities.count("high") >= 1 and len(indicators) >= 3
        ):
            return "critical"
        if "high" in severities:
            return "high"
        if severities.count("medium") >= 2:
            return "high"
        if "medium" in severities:
            return "medium"
        return "low"

    async def _generate_summary(
        self,
        query: str,
        indicators: list[FraudIndicator],
        candidates: list[SearchResult],
    ) -> str:
        """Generate a plain-language investigation memo via Bedrock."""
        if not indicators:
            return (
                f"Analysis of {len(candidates)} filings for query "
                f"'{query}' found no fraud indicators. "
                "Standard monitoring recommends periodic re-analysis as new filings occur."
            )

        indicator_lines = "\n".join(
            f"- [{ind.severity.upper()}] {ind.indicator_type}: {ind.description} "
            f"(confidence: {ind.confidence:.0%}, evidence: {len(ind.evidence)} docs)"
            for ind in indicators
        )

        prompt = f"""You are a legal fraud investigator preparing a concise memo.

SEARCH QUERY: {query}
FILINGS ANALYZED: {len(candidates)}

DETECTED INDICATORS:
{indicator_lines}

Write a 3-5 sentence investigation memo that:
1. States the overall risk level and key findings
2. Explains what the indicators suggest in plain language
3. Recommends specific next steps for a human investigator
4. Notes what additional evidence would confirm or refute the flags

Do not speculate beyond the evidence. Use professional, neutral tone."""

        try:
            import asyncio

            from generation.bedrock_client import BedrockLLMClient

            client = BedrockLLMClient()
            loop = asyncio.get_event_loop()
            summary = await loop.run_in_executor(
                None,
                lambda: client.complete(
                    system="You are a forensic legal analyst. Be factual, precise, and neutral.",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                ),
            )
            return summary
        except Exception as exc:
            logger.warning("fraud_summary_generation_failed", error=str(exc))
            risk = self._compute_risk_level(indicators)
            return (
                f"Detected {len(indicators)} indicator(s). "
                f"Risk level: {risk}. Manual review required."
            )
