from __future__ import annotations

from pydantic import BaseModel, Field


class FraudAnalysisRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description=(
            "Search context for fraud analysis — e.g. party name, address, "
            "case number, or filing type (deed, motion, etc.)."
        ),
    )


class FraudIndicatorItem(BaseModel):
    indicator_type: str
    severity: str  # "low" | "medium" | "high" | "critical"
    description: str
    evidence: list[str]  # source_ids supporting this indicator
    confidence: float


class FraudAnalysisResponse(BaseModel):
    run_id: str
    query_context: str
    risk_level: str  # "none" | "low" | "medium" | "high" | "critical"
    requires_human_review: bool
    total_filings_analyzed: int
    flagged_source_ids: list[str]
    summary: str
    indicators: list[FraudIndicatorItem]
