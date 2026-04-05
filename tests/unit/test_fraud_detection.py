"""Unit tests for agents.fraud_detection_agent._FilingPatternAnalyzer."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from agents.fraud_detection_agent import FraudIndicator, _FilingPatternAnalyzer
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
