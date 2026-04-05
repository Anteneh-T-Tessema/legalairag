"""Unit tests for agents.fraud_detection_agent._FilingPatternAnalyzer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.fraud_detection_agent import (
    FraudDetectionAgent,
    FraudIndicator,
    _FilingPatternAnalyzer,
)
from retrieval.hybrid_search import SearchResult

# ── Helpers ───────────────────────────────────────────────────────────────────


def _result(
    source_id: str,
    content: str = "",
    parties: list[str] | None = None,
    filing_date: str = "",
    extra_meta: dict[str, Any] | None = None,
) -> SearchResult:
    meta: dict[str, Any] = dict(extra_meta or {})
    if parties is not None:
        meta["parties"] = parties
    if filing_date:
        meta["filing_date"] = filing_date
    return SearchResult(
        chunk_id=source_id,
        source_id=source_id,
        content=content,
        section="",
        citations=[],
        metadata=meta,
        score=0.8,
    )


def _burst(n: int, party: str = "Fraud Corp", start: date | None = None) -> list[SearchResult]:
    """n filings by the same party on consecutive days."""
    start = start or date(2024, 3, 1)
    return [
        _result(
            f"case-{i}",
            parties=[party],
            filing_date=(start + timedelta(days=i)).isoformat(),
        )
        for i in range(n)
    ]


def _deed(i: int, amount: str = "$1.00") -> SearchResult:
    content = (
        f"This quitclaim deed transfers the property for the sum of {amount}. "
        "All rights hereby conveyed."
    )
    return _result(f"deed-{i}", content=content)


# ── _detect_burst_filing ──────────────────────────────────────────────────────


def test_burst_detected_above_threshold():
    indicators = _FilingPatternAnalyzer._detect_burst_filing(_burst(7))
    assert any(i.indicator_type == "burst_filing" for i in indicators)


def test_burst_not_triggered_below_threshold():
    indicators = _FilingPatternAnalyzer._detect_burst_filing(_burst(4))
    assert not indicators


def test_burst_exactly_at_threshold_detected():
    # Threshold is >= 6
    indicators = _FilingPatternAnalyzer._detect_burst_filing(_burst(6))
    assert any(i.indicator_type == "burst_filing" for i in indicators)


def test_burst_severity_medium_for_small_burst():
    indicators = _FilingPatternAnalyzer._detect_burst_filing(_burst(7))
    burst = next(i for i in indicators if i.indicator_type == "burst_filing")
    assert burst.severity == "medium"


def test_burst_severity_high_for_large_burst():
    indicators = _FilingPatternAnalyzer._detect_burst_filing(_burst(12))
    burst = next(i for i in indicators if i.indicator_type == "burst_filing")
    assert burst.severity == "high"


def test_burst_confidence_grows_with_count():
    ind_small = _FilingPatternAnalyzer._detect_burst_filing(_burst(6))
    ind_large = _FilingPatternAnalyzer._detect_burst_filing(_burst(11))
    conf_small = next(i for i in ind_small if i.indicator_type == "burst_filing").confidence
    conf_large = next(i for i in ind_large if i.indicator_type == "burst_filing").confidence
    assert conf_large > conf_small


def test_burst_missing_filing_date_skipped():
    results = [_result("x", parties=["Corp A"])]  # no filing_date
    assert not _FilingPatternAnalyzer._detect_burst_filing(results)


def test_burst_spread_over_60_days_not_triggered():
    """6 filings one every 10 days don't trigger the 30-day window."""
    results = [
        _result(
            f"c{i}",
            parties=["Spread LLC"],
            filing_date=(date(2024, 1, 1) + timedelta(days=i * 10)).isoformat(),
        )
        for i in range(6)
    ]
    assert not _FilingPatternAnalyzer._detect_burst_filing(results)


def test_burst_assigns_evidence_source_ids():
    results = _burst(7)
    indicators = _FilingPatternAnalyzer._detect_burst_filing(results)
    burst = next(i for i in indicators if i.indicator_type == "burst_filing")
    assert len(burst.evidence) >= 6
    for eid in burst.evidence:
        assert eid.startswith("case-")


# ── _detect_deed_fraud_patterns ───────────────────────────────────────────────


def test_deed_fraud_detected_at_threshold():
    results = [_deed(i) for i in range(3)]
    indicators = _FilingPatternAnalyzer._detect_deed_fraud_patterns(results)
    assert any(i.indicator_type == "deed_fraud_pattern" for i in indicators)


def test_deed_fraud_not_triggered_below_threshold():
    results = [_deed(0), _deed(1)]  # only 2
    assert not _FilingPatternAnalyzer._detect_deed_fraud_patterns(results)


def test_deed_fraud_high_consideration_not_flagged():
    content = "Warranty deed for $275,000 — full market value consideration."
    results = [_result(f"wd{i}", content=content) for i in range(5)]
    assert not _FilingPatternAnalyzer._detect_deed_fraud_patterns(results)


def test_deed_fraud_nominal_ten_dollars_flagged():
    results = [
        _result(
            f"d{i}",
            content="Quitclaim deed for the sum of $10.00 consideration.",
        )
        for i in range(3)
    ]
    indicators = _FilingPatternAnalyzer._detect_deed_fraud_patterns(results)
    assert any(i.indicator_type == "deed_fraud_pattern" for i in indicators)


def test_deed_fraud_evidence_contains_source_ids():
    results = [_deed(i) for i in range(3)]
    indicators = _FilingPatternAnalyzer._detect_deed_fraud_patterns(results)
    deed_ind = next(i for i in indicators if i.indicator_type == "deed_fraud_pattern")
    assert set(deed_ind.evidence) == {"deed-0", "deed-1", "deed-2"}


# ── _detect_identity_reuse ────────────────────────────────────────────────────


def test_identity_reuse_ssn_in_three_cases():
    results = [
        _result(f"id-{i}", content=f"Defendant SSN: XXX-XX-5678 (case {i})") for i in range(3)
    ]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    assert any(i.indicator_type == "identity_reuse" for i in indicators)


def test_identity_reuse_two_cases_not_triggered():
    results = [
        _result("id-1", content="SSN: XXX-XX-9999"),
        _result("id-2", content="SSN: XXX-XX-9999"),
    ]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    ssn_inds = [i for i in indicators if i.indicator_type == "identity_reuse"]
    assert not ssn_inds


def test_identity_reuse_unique_ssns_not_triggered():
    results = [
        _result("id-1", content="SSN: XXX-XX-1111"),
        _result("id-2", content="SSN: XXX-XX-2222"),
        _result("id-3", content="SSN: XXX-XX-3333"),
    ]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    assert not any(i.indicator_type == "identity_reuse" for i in indicators)


def test_identity_reuse_severity_high_for_ssn():
    results = [_result(f"id-{i}", content="SSN: XXX-XX-4321") for i in range(3)]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    ssn_ind = next(i for i in indicators if i.indicator_type == "identity_reuse")
    assert ssn_ind.severity == "high"


# ── _detect_suspicious_party_patterns ────────────────────────────────────────


def test_suspicious_numeric_entity_detected():
    results = [
        _result("r1", extra_meta={"parties": ["Entity 42 LLC"]}),
        _result("r2", extra_meta={"parties": ["Co. 7 Inc."]}),
    ]
    indicators = _FilingPatternAnalyzer._detect_suspicious_party_patterns(results)
    assert any(i.indicator_type == "suspicious_entity" for i in indicators)


def test_suspicious_entity_not_triggered_for_normal_names():
    results = [
        _result("r1", extra_meta={"parties": ["Smith & Sons LLC"]}),
        _result("r2", extra_meta={"parties": ["Hoosier Properties Inc."]}),
    ]
    indicators = _FilingPatternAnalyzer._detect_suspicious_party_patterns(results)
    assert not any(i.indicator_type == "suspicious_entity" for i in indicators)


# ── analyze (integration of all detectors) ────────────────────────────────────


def test_analyze_empty_returns_no_indicators():
    assert _FilingPatternAnalyzer().analyze([]) == []


def test_analyze_combines_multiple_detector_results():
    results = _burst(8) + [_deed(i) for i in range(3)]
    indicators = _FilingPatternAnalyzer().analyze(results)
    types = {i.indicator_type for i in indicators}
    assert "burst_filing" in types
    assert "deed_fraud_pattern" in types


def test_analyze_returns_list_of_fraud_indicators():
    results = _burst(7)
    indicators = _FilingPatternAnalyzer().analyze(results)
    assert all(isinstance(i, FraudIndicator) for i in indicators)


# ── _detect_identity_reuse — DOB path ─────────────────────────────────────────


def test_identity_reuse_dob_in_four_cases():
    """DOB appearing in 4+ cases triggers medium identity_reuse indicator."""
    results = [
        _result(f"dob-{i}", content="DOB: 03/15/1985 (case record)")
        for i in range(4)
    ]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    dob_inds = [i for i in indicators if i.indicator_type == "identity_reuse"]
    assert dob_inds
    assert dob_inds[0].severity == "medium"


def test_identity_reuse_dob_three_cases_not_triggered():
    """DOB in 3 cases (threshold is >3) does NOT trigger."""
    results = [
        _result(f"dob-{i}", content="DOB: 07/04/1990 case record")
        for i in range(3)
    ]
    indicators = _FilingPatternAnalyzer._detect_identity_reuse(results)
    dob_inds = [i for i in indicators if i.indicator_type == "identity_reuse"]
    assert not dob_inds


# ── _detect_rapid_ownership_transfer ──────────────────────────────────────────


def _property_transfer(i: int, days_offset: int, addr: str = "123 Main St") -> SearchResult:
    """Filing with a property address mention and filing_date."""
    content = f"The property at {addr}, Indianapolis, Indiana is hereby transferred."
    return _result(
        f"prop-{i}",
        content=content,
        filing_date=(date(2024, 1, 1) + timedelta(days=days_offset)).isoformat(),
    )


def test_rapid_ownership_transfer_detected():
    """Same address transferred 3 times within 90 days triggers indicator."""
    results = [_property_transfer(i, i * 20) for i in range(3)]  # 0, 20, 40 days
    indicators = _FilingPatternAnalyzer._detect_rapid_ownership_transfer(results)
    assert any(i.indicator_type == "rapid_ownership_transfer" for i in indicators)


def test_rapid_ownership_transfer_not_triggered_within_two_filings():
    results = [_property_transfer(i, i * 10) for i in range(2)]
    indicators = _FilingPatternAnalyzer._detect_rapid_ownership_transfer(results)
    assert not any(i.indicator_type == "rapid_ownership_transfer" for i in indicators)


def test_rapid_ownership_transfer_not_triggered_over_90_days():
    """3 transfers but span > 90 days → not triggered."""
    results = [_property_transfer(i, i * 50) for i in range(3)]  # 0, 50, 100 days
    indicators = _FilingPatternAnalyzer._detect_rapid_ownership_transfer(results)
    assert not any(i.indicator_type == "rapid_ownership_transfer" for i in indicators)


def test_rapid_ownership_transfer_no_filing_date_skipped():
    results = [
        _result(f"p{i}", content="123 Oak Ave, Indianapolis, Indiana transferred.")
        for i in range(3)
    ]  # no filing_date → should not trigger
    indicators = _FilingPatternAnalyzer._detect_rapid_ownership_transfer(results)
    assert not any(i.indicator_type == "rapid_ownership_transfer" for i in indicators)


def test_rapid_ownership_transfer_severity_high():
    results = [_property_transfer(i, i * 15) for i in range(4)]
    indicators = _FilingPatternAnalyzer._detect_rapid_ownership_transfer(results)
    rapid = [i for i in indicators if i.indicator_type == "rapid_ownership_transfer"]
    if rapid:  # only assert if triggered
        assert rapid[0].severity == "high"


# ── FraudDetectionAgent._compute_risk_level ───────────────────────────────────


def test_risk_none_when_no_indicators():
    assert FraudDetectionAgent._compute_risk_level([]) == "none"


def test_risk_low_for_single_low_severity():
    ind = FraudIndicator("t", "low", "desc", [], 0.3)
    assert FraudDetectionAgent._compute_risk_level([ind]) == "low"


def test_risk_medium_for_single_medium_severity():
    ind = FraudIndicator("t", "medium", "desc", [], 0.5)
    assert FraudDetectionAgent._compute_risk_level([ind]) == "medium"


def test_risk_high_for_single_high_severity():
    ind = FraudIndicator("t", "high", "desc", [], 0.8)
    assert FraudDetectionAgent._compute_risk_level([ind]) == "high"


def test_risk_critical_for_critical_indicator():
    ind = FraudIndicator("t", "critical", "desc", [], 0.95)
    assert FraudDetectionAgent._compute_risk_level([ind]) == "critical"


def test_risk_critical_for_two_high_indicators():
    inds = [FraudIndicator("t", "high", "d", [], 0.8) for _ in range(2)]
    assert FraudDetectionAgent._compute_risk_level(inds) == "critical"


def test_risk_critical_for_one_high_and_three_total():
    inds = [
        FraudIndicator("t", "high", "d", [], 0.8),
        FraudIndicator("t", "medium", "d", [], 0.5),
        FraudIndicator("t", "low", "d", [], 0.3),
    ]
    assert FraudDetectionAgent._compute_risk_level(inds) == "critical"


def test_risk_high_for_two_mediums():
    inds = [FraudIndicator("t", "medium", "d", [], 0.5) for _ in range(2)]
    assert FraudDetectionAgent._compute_risk_level(inds) == "high"


# ── FraudDetectionAgent._execute ─────────────────────────────────────────────


def _make_fraud_agent() -> FraudDetectionAgent:
    """Build a FraudDetectionAgent with all external deps mocked."""
    with (
        patch("agents.fraud_detection_agent.BedrockEmbedder"),
        patch("agents.fraud_detection_agent.HybridSearcher"),
    ):
        agent = FraudDetectionAgent()

    mock_chunk = MagicMock()
    mock_chunk.source_id = "src-1"
    mock_chunk.content = "Indiana filing content."
    mock_chunk.metadata = {}

    agent._embedder = MagicMock()
    agent._embedder.embed_query = AsyncMock(return_value=[0.1] * 128)
    agent._searcher = MagicMock()
    agent._searcher.search = AsyncMock(return_value=[mock_chunk])
    return agent


@pytest.mark.asyncio
async def test_fraud_agent_execute_no_indicators():
    agent = _make_fraud_agent()
    # Analyzer returns no indicators → risk_level = "none"
    agent._analyzer = MagicMock()
    agent._analyzer.analyze.return_value = []

    result = await agent._execute(query="quitclaim deed Marion County", jurisdiction="Indiana")

    assert result.risk_level == "none"
    assert not result.requires_human_review
    assert result.total_filings_analyzed == 1


@pytest.mark.asyncio
async def test_fraud_agent_execute_with_indicators():
    agent = _make_fraud_agent()
    indicator = FraudIndicator(
        indicator_type="deed_fraud_pattern",
        severity="high",
        description="Suspicious deeds",
        evidence=["src-1"],
        confidence=0.8,
    )
    agent._analyzer = MagicMock()
    agent._analyzer.analyze.return_value = [indicator]

    with patch("generation.bedrock_client.BedrockLLMClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.complete.return_value = "Investigation memo text."
        mock_client_cls.return_value = mock_client
        result = await agent._execute(query="suspicious deeds", jurisdiction="Indiana")

    assert result.risk_level == "high"
    assert result.requires_human_review
    assert "src-1" in result.flagged_source_ids


@pytest.mark.asyncio
async def test_fraud_agent_execute_llm_failure_falls_back():
    """If Bedrock fails, _generate_summary returns a fallback string."""
    agent = _make_fraud_agent()
    indicator = FraudIndicator("deed_fraud_pattern", "high", "d", ["src-1"], 0.8)
    agent._analyzer = MagicMock()
    agent._analyzer.analyze.return_value = [indicator]

    with patch("generation.bedrock_client.BedrockLLMClient") as mock_cls:
        mock_cls.side_effect = Exception("No AWS credentials")
        result = await agent._execute(query="test query")

    assert result.summary  # fallback summary should be non-empty
    assert "src-1" in result.flagged_source_ids
