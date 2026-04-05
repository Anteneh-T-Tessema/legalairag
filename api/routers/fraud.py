from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agents.fraud_detection_agent import FraudAnalysisResult, FraudDetectionAgent
from api.auth import UserInfo, get_current_user
from api.schemas.fraud import FraudAnalysisRequest, FraudAnalysisResponse, FraudIndicatorItem

router = APIRouter(prefix="/fraud", tags=["fraud"])

_agent = FraudDetectionAgent()


@router.post("/analyze", response_model=FraudAnalysisResponse)
async def analyze_fraud(
    req: FraudAnalysisRequest,
    _user: UserInfo = Depends(get_current_user),
) -> FraudAnalysisResponse:
    """
    Run the fraud detection agent over Indiana legal filings matching the
    provided query context (e.g. a party name, case number, or address).

    Returns risk level, detected indicators, and flagged source IDs.
    Results are strictly advisory — no automated action is taken.
    The full run is persisted to the audit log with `run_id` for traceability.
    """
    try:
        result: FraudAnalysisResult = await _agent.run(query=req.query)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fraud detection failed: {exc}",
        ) from exc

    return FraudAnalysisResponse(
        run_id=result.run_id,
        query_context=result.query_context,
        risk_level=result.risk_level,
        requires_human_review=result.requires_human_review,
        total_filings_analyzed=result.total_filings_analyzed,
        flagged_source_ids=result.flagged_source_ids,
        summary=result.summary,
        indicators=[
            FraudIndicatorItem(
                indicator_type=ind.indicator_type,
                severity=ind.severity,
                description=ind.description,
                evidence=ind.evidence,
                confidence=round(ind.confidence, 4),
            )
            for ind in result.indicators
        ],
    )
