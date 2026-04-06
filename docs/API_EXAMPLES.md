# API Examples

Copy-paste cURL and Python snippets to get started with the IndyLeg API.

> **Base URL** — replace `$BASE` with your ALB DNS or CloudFront URL (e.g. `https://indyleg.example.com`).

---

## Authentication

### Login

```bash
# cURL
curl -s -X POST "$BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "attorney1", "password": "s3cur3p@ss"}'
```

```python
import httpx

resp = httpx.post(f"{BASE}/api/v1/auth/token", json={
    "username": "attorney1",
    "password": "s3cur3p@ss",
})
tokens = resp.json()
access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]
print(f"Logged in — expires in {tokens['expires_in']}s")
```

### Refresh Token

```bash
curl -s -X POST "$BASE/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

```python
resp = httpx.post(f"{BASE}/api/v1/auth/refresh", json={
    "refresh_token": refresh_token,
})
tokens = resp.json()
access_token = tokens["access_token"]
```

### Logout

```bash
curl -s -X POST "$BASE/api/v1/auth/logout" \
  -H "Authorization: Bearer $TOKEN"
```

### Get Current User

```bash
curl -s "$BASE/api/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Search (Hybrid Retrieval)

Find relevant document chunks without generating an answer.

```bash
curl -s -X POST "$BASE/api/v1/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "eviction notice requirements Marion County",
    "top_k": 5,
    "filters": {"jurisdiction": "Marion County"}
  }'
```

```python
headers = {"Authorization": f"Bearer {access_token}"}

resp = httpx.post(f"{BASE}/api/v1/search", headers=headers, json={
    "query": "eviction notice requirements Marion County",
    "top_k": 5,
    "filters": {"jurisdiction": "Marion County"},
})
for result in resp.json()["results"]:
    print(f"[{result['score']:.3f}] {result['text'][:120]}...")
```

---

## RAG — Ask a Question

Full pipeline: retrieval → re-ranking → generation → validation.

```bash
curl -s -X POST "$BASE/api/v1/search/ask" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the required notice period before evicting a tenant in Indiana?",
    "filters": {"jurisdiction": "Marion County"},
    "stream": false
  }'
```

```python
resp = httpx.post(f"{BASE}/api/v1/search/ask", headers=headers, json={
    "question": "What is the required notice period before evicting a tenant in Indiana?",
    "filters": {"jurisdiction": "Marion County"},
    "stream": False,
})
data = resp.json()
print(f"Answer ({data['confidence']}): {data['answer']}")
for src in data["sources"]:
    print(f"  - [{src['score']:.2f}] {src['source_id']}")
```

---

## Fraud Detection

Analyse filings for suspicious patterns. Results are advisory only.

```bash
curl -s -X POST "$BASE/api/v1/fraud/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "quitclaim deed Marion County 2024"}'
```

```python
resp = httpx.post(f"{BASE}/api/v1/fraud/analyze", headers=headers, json={
    "query": "quitclaim deed Marion County 2024",
})
report = resp.json()
print(f"Risk: {report['risk_level']} — {report['total_filings_analyzed']} filings")
for ind in report["indicators"]:
    print(f"  [{ind['severity']}] {ind['indicator_type']}: {ind['description']}")
```

---

## Document Ingestion

Queue a document for processing (chunking → embedding → indexing).

```bash
curl -s -X POST "$BASE/api/v1/documents/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_url": "https://mycase.in.gov/case/49D01-2024-PL-000123",
    "source_type": "court_filing",
    "metadata": {"jurisdiction": "Marion County"}
  }'
```

```python
resp = httpx.post(f"{BASE}/api/v1/documents/ingest", headers=headers, json={
    "source_url": "https://mycase.in.gov/case/49D01-2024-PL-000123",
    "source_type": "court_filing",
    "metadata": {"jurisdiction": "Marion County"},
})
print(resp.json())  # {"message": "Document queued", "job_id": "..."}
```

---

## Health & Metrics

> **Note**: `/health`, `/metrics`, and `/metrics/json` are root-level routes, not under `/api/v1`.

```bash
# Health check (no auth)
curl -s "$BASE/health"

# Prometheus metrics (admin)
curl -s "$BASE/metrics" -H "Authorization: Bearer $ADMIN_TOKEN"

# JSON metrics (admin)
curl -s "$BASE/metrics/json" -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Helper: Full Session Script

```bash
#!/usr/bin/env bash
set -euo pipefail
BASE="https://indyleg.example.com"

# 1. Login
TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username":"attorney1","password":"s3cur3p@ss"}' | jq -r .access_token)

# 2. Search
curl -s -X POST "$BASE/api/v1/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"child custody modification","top_k":3}' | jq .

# 3. Ask
curl -s -X POST "$BASE/api/v1/search/ask" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I modify a custody order in Indiana?","stream":false}' | jq .

# 4. Logout
curl -s -X POST "$BASE/api/v1/auth/logout" \
  -H "Authorization: Bearer $TOKEN"
```
