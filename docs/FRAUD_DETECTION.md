# Fraud Detection System

This document describes the IndyLeg fraud detection subsystem in detail.

---

## Overview

The `FraudDetectionAgent` scans Indiana legal filings for anomaly patterns that suggest fraudulent activity. It is a **detection-only** system — all findings are advisory and require human investigator review. No automated enforcement actions are taken.

Key design principles:
- **Read-only**: The agent only reads from the document store; it cannot modify or delete records
- **Auditable**: Every analysis run generates an `AgentRun` record with a UUID `run_id`
- **Conservative**: Indicators have explicit confidence scores; the system favors false positives over false negatives
- **Extensible**: Adding a new detector is as simple as adding a `_detect_*` method to `_FilingPatternAnalyzer`

---

## Pipeline

```text
Query ("quitclaim deed Marion County")
    │
    ▼
Step 1: Parse + Embed Query
    │  QueryParser → normalized query + metadata
    │  BedrockEmbedder → 1024-dim vector
    ▼
Step 2: Retrieve Filings (top_k=50)
    │  HybridSearcher → wide candidate set for pattern analysis
    ▼
Step 3: Pattern Analysis
    │  _FilingPatternAnalyzer.analyze()
    │  → runs all 5 detectors in sequence
    ▼
Step 4: Risk Scoring
    │  Aggregates indicator severities into overall risk level
    ▼
Step 5: Investigation Summary
    │  Bedrock Claude generates human-readable memo
    ▼
Step 6: Persist Audit Trail
    │  AgentRun + FraudAnalysisResult + all indicators
    ▼
FraudAnalysisResult
```

---

## Pattern Detectors

### 1. Burst Filing Detection

**What it detects**: The same party name appearing in an unusually high number of filings within a short time window. Legitimate litigants rarely file dozens of cases in a week.

**Algorithm**:
- Group all filings by party name (case-insensitive)
- Sort filings by date within each party
- Slide a 30-day window across the timeline
- Flag if any window contains ≥6 filings

**Thresholds**:
- 6-9 filings → `severity: "medium"`
- 10+ filings → `severity: "high"`
- Confidence: `0.60 + (count - 6) * 0.05`, capped at 0.95

---

### 2. Identity Reuse Detection

**What it detects**: The same personal identifiers (SSN fragments, dates of birth, addresses) appearing across multiple unrelated cases with different party names — a strong indicator of identity theft.

**Identifiers scanned**:
- SSN last-4 fragments (`XXX-XX-1234`)
- Dates of birth (`DOB: 01/15/1980`)
- Street addresses (`123 Main St`)

**Thresholds**:
- SSN fragment in >2 cases → `severity: "high"`, confidence 0.75
- DOB in >3 cases → `severity: "medium"`, confidence 0.55
- Address matches are counted but not independently flagged (supporting evidence)

---

### 3. Deed Fraud Pattern Detection

**What it detects**: Serial quitclaim deeds with nominal consideration ($1, $10, $100) — a common pattern in property fraud where ownership is transferred fraudulently using low-value quitclaim deeds.

**Algorithm**:
- Scan filing text for `quitclaim deed` mentions
- Check for nominal consideration patterns (`$1.00`, `$10.00`, `$100`)
- Flag when ≥3 matching filings appear

**Threshold**: ≥3 cases → `severity: "high"`, confidence 0.80

---

### 4. Suspicious Entity Detection

**What it detects**: Cases involving numerically-named entities (e.g., "Entity 42 LLC", "Co. 7") that are commonly used in shell company fraud.

**Algorithm**:
- Scan party names in filing metadata
- Match against `Entity\s*\d+` and `Co.\s*\d+` patterns

**Threshold**: ≥2 cases → `severity: "medium"`, confidence 0.50

---

### 5. Rapid Ownership Transfer Detection

**What it detects**: A single property address changing hands 3 or more times within 90 days — a common pattern in property flipping schemes and title fraud.

**Algorithm**:
- Extract property addresses from filing text (Indianapolis/Indiana addresses)
- Group filings by address
- Check date span for each address group
- Flag if ≥3 unique source IDs within a 90-day span

**Threshold**: ≥3 transfers in 90 days → `severity: "high"`, confidence 0.70

---

## Risk Level Computation

The overall risk level is computed by aggregating individual indicator severities:

| Risk Level | Condition |
|---|---|
| `critical` | Any indicator with `severity="critical"` OR ≥3 high-severity indicators |
| `high` | Any high-severity indicator |
| `medium` | Any medium-severity indicator |
| `low` | Only low-severity indicators |
| `none` | No indicators detected |

Results with `risk_level ∈ {medium, high, critical}` automatically set `requires_human_review=True`.

---

## API Endpoint

```http
POST /api/v1/fraud/analyze
Authorization: Bearer <token>
Content-Type: application/json
```

### Request

```json
{
  "query": "quitclaim deed Marion County 2024"
}
```

### Response

```json
{
  "run_id": "d4e5f6a7-b8c9-0123-4567-89abcdef0123",
  "query_context": "quitclaim deed Marion County 2024",
  "risk_level": "high",
  "requires_human_review": true,
  "total_filings_analyzed": 47,
  "flagged_source_ids": [
    "case-49D01-2024-PL-000123",
    "case-49D01-2024-PL-000456"
  ],
  "summary": "Investigation found 3 quitclaim deeds with nominal consideration...",
  "indicators": [
    {
      "indicator_type": "deed_fraud_pattern",
      "severity": "high",
      "description": "Found 3 quitclaim deeds with nominal consideration ($1-$100).",
      "evidence": [
        "case-49D01-2024-PL-000123",
        "case-49D01-2024-PL-000456",
        "case-49D01-2024-PL-000789"
      ],
      "confidence": 0.80
    }
  ]
}
```

---

## Adding New Detectors

To add a new pattern detector:

1. Add a static method to `_FilingPatternAnalyzer` following the `_detect_*` convention:

```python
@staticmethod
def _detect_new_pattern(results: list[SearchResult]) -> list[FraudIndicator]:
    """Docstring explaining what this detector looks for."""
    indicators: list[FraudIndicator] = []
    # ... pattern analysis logic ...
    return indicators
```

1. Register it in the `analyze()` method:

```python
def analyze(self, results: list[SearchResult]) -> list[FraudIndicator]:
    indicators: list[FraudIndicator] = []
    # ... existing detectors ...
    indicators.extend(self._detect_new_pattern(results))
    return indicators
```

1. Add unit tests in `tests/unit/test_fraud_detection.py`.

---

## Test Coverage

The fraud detection system is tested in `tests/unit/test_fraud_detection.py` covering:

- Each detector individually with crafted `SearchResult` fixtures
- Edge cases: empty result sets, missing metadata, malformed dates
- Risk level computation across severity combinations
- Integration with `BaseAgent` audit trail
