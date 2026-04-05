from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    jurisdiction: str | None = Field(None, description="Indiana county or 'Indiana'")
    case_type: str | None = Field(None, description="e.g. Criminal, Civil, Family")
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    chunk_id: str
    source_id: str
    section: str
    content: str
    citations: list[str]
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    jurisdiction: str | None
    total: int


class AskRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    jurisdiction: str | None = None
    case_type: str | None = None


class AskResponse(BaseModel):
    query: str
    answer: str
    source_ids: list[str]
    citations: list[str]
    confidence: str
    run_id: str
    validation_passed: bool
