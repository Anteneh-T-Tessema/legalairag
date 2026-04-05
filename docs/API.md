# API Reference

Complete API reference for the IndyLeg FastAPI backend.

**Base URL**: `https://your-alb-dns/api/v1`

All endpoints except `/auth/token` and `/health` require `Authorization: Bearer <token>`.

---

## Authentication

### `POST /auth/token` — Login

Authenticate with username and password to receive JWT tokens.

**Request:**
```json
{
  "username": "attorney1",
  "password": "s3cur3p@ss"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Response `401 Unauthorized`:**
```json
{ "detail": "Invalid credentials" }
```

### `POST /auth/refresh` — Refresh Access Token

**Request:**
```json
{ "refresh_token": "eyJ..." }
```

**Response `200 OK`:**
```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600 }
```

### `GET /auth/me` — Current User Profile

**Response `200 OK`:**
```json
{
  "user_id": "usr-001",
  "username": "attorney1",
  "roles": ["attorney"],
  "email": "attorney1@example.com"
}
```

---

## Search & RAG

### `POST /search` — Hybrid Retrieval

Returns ranked document chunks without generating an answer. Useful for document exploration.

**Request:**
```json
{
  "query": "eviction notice requirements Marion County",
  "top_k": 10,
  "filters": {
    "jurisdiction": "Marion County",
    "case_type": "civil"
  }
}
```

**Response `200 OK`:**
```json
{
  "query": "eviction notice requirements Marion County",
  "results": [
    {
      "chunk_id": "case-49D01-2023-MF-001234-chunk-003",
      "text": "Indiana Code § 32-31-1-6 requires the landlord to provide...",
      "source_id": "case-49D01-2023-MF-001234",
      "source_type": "court_filing",
      "score": 0.923,
      "metadata": {
        "jurisdiction": "Marion County",
        "case_type": "civil",
        "citations": ["IC 32-31-1-6"],
        "section_heading": "FINDINGS OF FACT",
        "page_number": 3
      }
    }
  ],
  "total": 10,
  "search_time_ms": 145
}
```

### `POST /search/ask` — RAG Answer Generation

Runs the full CaseResearchAgent pipeline: retrieval → re-ranking → generation → validation.

**Request:**
```json
{
  "question": "What is the required notice period before evicting a tenant in Indiana?",
  "filters": {
    "jurisdiction": "Marion County"
  },
  "stream": false
}
```

**Response `200 OK`:**
```json
{
  "answer": "Under Indiana law, a landlord must provide at least 10 days written notice [SOURCE: chunk-003]...",
  "sources": [
    {
      "chunk_id": "chunk-003",
      "text": "IC 32-31-1-6 provides that...",
      "source_id": "case-49D01-2023-MF-001234",
      "score": 0.923
    }
  ],
  "confidence": "HIGH",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "validation": {
    "passed": true,
    "warnings": []
  },
  "latency_ms": 1420
}
```

---

## Fraud Detection

### `POST /fraud/analyze` — Fraud Pattern Analysis

Runs the FraudDetectionAgent over filings matching the query. Returns risk assessment and detected anomaly indicators. All results are strictly advisory — no automated actions are taken.

**Request:**
```json
{
  "query": "quitclaim deed Marion County 2024"
}
```

**Response `200 OK`:**
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
      "evidence": ["case-49D01-2024-PL-000123", "case-49D01-2024-PL-000456"],
      "confidence": 0.80
    }
  ]
}
```

**Risk Levels**: `none` | `low` | `medium` | `high` | `critical`

**Indicator Types**: `burst_filing` | `identity_reuse` | `deed_fraud_pattern` | `suspicious_entity` | `rapid_ownership_transfer`

---

## Health

### `GET /health`

No authentication required.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "ok",
    "opensearch": "ok",
    "bedrock": "ok"
  }
}
```

---

## Error Responses

All error responses follow the standard format:

```json
{
  "detail": "Error description"
}
```

| Status Code | Meaning |
|---|---|
| `400` | Bad request — invalid input |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient role |
| `404` | Resource not found |
| `422` | Validation error — Pydantic schema mismatch |
| `429` | Rate limited |
| `500` | Internal server error |

---

## Authentication Notes

- **Access tokens** expire after 60 minutes
- **Refresh tokens** expire after 7 days
- Tokens are signed with HS256 using the `API_SECRET_KEY`
- The `Authorization: Bearer <token>` header is required for all protected endpoints
- Role requirements are enforced per-endpoint via the `require_role()` decorator

### Roles

| Role | Access Level |
|---|---|
| `ADMIN` | All endpoints + ingestion management |
| `ATTORNEY` | Search, RAG answers, fraud analysis, document viewer |
| `CLERK` | Search, document upload |
| `VIEWER` | Read-only search |
