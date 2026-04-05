from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.schemas.documents import IngestRequest, IngestResponse
from ingestion.queue.sqs import IngestionMessage, SQSProducer

router = APIRouter(prefix="/documents", tags=["documents"])

_producer = SQSProducer()


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(req: IngestRequest) -> IngestResponse:
    """
    Queue a document for async ingestion.
    Returns immediately; actual processing happens in the background worker.
    """
    msg = IngestionMessage(
        source_type=req.source_type,
        source_id=req.source_id,
        download_url=req.download_url,
        metadata=req.metadata,
    )
    try:
        message_id = await _producer.publish(msg)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to queue document: {exc}",
        ) from exc

    return IngestResponse(
        message_id=message_id,
        source_id=req.source_id,
        queued=True,
    )
