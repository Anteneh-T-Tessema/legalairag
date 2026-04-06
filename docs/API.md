# API Reference

Complete API reference for the IndyLeg FastAPI backend.

**Base URL**: `https://your-alb-dns/api/v1`
**Version**: 0.7.0 | **Date**: April 2026

All endpoints except `/auth/token`, `/health`, and `/metrics` require `Authorization: Bearer <token>`.

> **Note**: `/health`, `/metrics`, and `/metrics/json` are mounted at the **root level** (e.g., `http://host:8000/health`), not under `/api/v1`. All other endpoints are under `/api/v1`.

### Endpoint Summary

| Method | Path | Auth | Roles | Description |
|---|---|---|---|---|
| POST | `/auth/token` | No | Any | Login |
| POST | `/auth/refresh` | No | Any | Refresh access token (with rotation) |
| POST | `/auth/logout` | Yes | Any | Logout (revoke current token) |
| POST | `/auth/revoke` | Yes | ADMIN | Revoke any token |
| GET | `/auth/me` | Yes | Any | Current user profile |
| POST | `/search` | Yes | Any | Hybrid retrieval search |
| POST | `/search/ask` | Yes | ADMIN, ATTORNEY, CLERK | RAG answer generation |
| POST | `/fraud/analyze` | Yes | ADMIN, ATTORNEY | Fraud pattern analysis |
| POST | `/documents/ingest` | Yes | ADMIN, ATTORNEY | Start document ingestion |
| GET | `/health` | No | — | Health check |
| GET | `/metrics` | Yes | ADMIN | Prometheus metrics |
| GET | `/metrics/json` | Yes | ADMIN | Metrics in JSON format |

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

Exchanges a valid refresh token for a new access/refresh token pair. The old refresh token is **revoked** after use (rotation).

**Request:**
```json
{ "refresh_token": "eyJ..." }
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJ...(new)...",
  "refresh_token": "eyJ...(new, rotated)...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

> **Note**: Each refresh token can only be used once. After refresh, the old refresh token is added to the revocation blacklist.

### `POST /auth/logout` — Logout

Revokes the current access token. The token is added to the blacklist and will be rejected on subsequent use.

**Headers:** `Authorization: Bearer <access_token>`

**Response `200 OK`:**
```json
{ "message": "Successfully logged out" }
```

### `POST /auth/revoke` — Revoke Token (Admin Only)

Allows administrators to revoke any user's token.

**Required Role**: `ADMIN`

**Request:**
```json
{ "token": "eyJ...(token to revoke)..." }
```

**Response `200 OK`:**
```json
{ "message": "Token revoked" }
```

**Response `403 Forbidden`:**
```json
{ "detail": "Insufficient permissions" }
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

## Health & Monitoring

> **Note**: These endpoints are at the **root level**, not under `/api/v1`.

### `GET /health`

No authentication required.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "env": "development"
}
```

### `GET /metrics` — Prometheus Metrics

Returns metrics in Prometheus text exposition format.

**Required Role**: `ADMIN`

**Response `200 OK`** (Content-Type: text/plain):
```text
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",endpoint="/search/ask",status="200"} 142
http_request_duration_seconds_bucket{endpoint="/search/ask",le="1.0"} 89
...
```

### `GET /metrics/json` — JSON Metrics

Returns the same metrics as `/metrics` in JSON format for programmatic consumption.

**Required Role**: `ADMIN`

**Response `200 OK`:**
```json
{
  "requests": {
    "total": 1420,
    "by_endpoint": {
      "/search/ask": 580,
      "/search": 340,
      "/fraud/analyze": 120,
      "/auth/token": 380
    }
  },
  "latency": {
    "p50_ms": 450,
    "p95_ms": 1800,
    "p99_ms": 3200
  },
  "rate_limits": {
    "total_hits": 23
  }
}
```

---

## Document Ingestion

### `POST /documents/ingest` — Start Document Ingestion

Queues a document for ingestion via the SQS pipeline. The document is downloaded, parsed, chunked, embedded, and indexed asynchronously.

**Required Roles**: `ADMIN`, `ATTORNEY`

**Request:**
```json
{
  "source_url": "https://courts.indiana.gov/filings/49D01-2024-CT-001234.pdf",
  "document_type": "court_filing",
  "metadata": {
    "jurisdiction": "Marion County",
    "case_type": "civil"
  }
}
```

**Response `202 Accepted`:**
```json
{
  "message": "Document queued for ingestion",
  "ingestion_id": "ing-a1b2c3d4"
}
```

---

## Rate Limiting

All authenticated endpoints are subject to rate limiting.

**Default**: 60 requests per minute per client IP.

**Response Headers** (on every request):
```text
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1713200460
```

**Response `429 Too Many Requests`:**
```json
{ "detail": "Rate limit exceeded. Try again in 15 seconds." }
```
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
