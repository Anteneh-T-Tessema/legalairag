from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    source_type: str  # "indiana_courts" | "s3_upload"
    source_id: str
    download_url: str
    metadata: dict = {}


class IngestResponse(BaseModel):
    message_id: str
    source_id: str
    queued: bool
