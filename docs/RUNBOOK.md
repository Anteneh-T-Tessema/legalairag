# Operations Runbook

**Project**: IndyLeg — Indiana Legal AI RAG Platform
**Version**: 0.2.0 | **Date**: April 2026

---

## Table of Contents

- [1. System Overview](#1-system-overview)
- [2. Monitoring](#2-monitoring)
- [3. Health Checks](#3-health-checks)
- [4. Common Issues & Resolutions](#4-common-issues--resolutions)
- [5. Incident Response](#5-incident-response)
- [6. Scaling](#6-scaling)
- [7. Backup & Recovery](#7-backup--recovery)
- [8. Operational Tasks](#8-operational-tasks)
- [9. Contacts & Escalation](#9-contacts--escalation)

---

## 1. System Overview

```text
Component          Service              Port/Endpoint
─────────────────────────────────────────────────────
API Server         ECS Fargate          ALB → :8000
Ingestion Worker   ECS Fargate          —
PostgreSQL         Aurora (pgvector)    :5432
OpenSearch         OpenSearch Service   :443
Redis              ElastiCache          :6379
Queue              SQS                  —
Object Store       S3                   —
LLM                Bedrock              —
Frontend           S3 + CloudFront      :443
```

### Key URLs

| Environment | API | UI | Metrics |
|---|---|---|---|
| Local | http://localhost:8000 | http://localhost:3000 | http://localhost:8000/metrics |
| Staging | https://api-staging.indyleg.com | https://staging.indyleg.com | https://api-staging.indyleg.com/metrics |
| Production | https://api.indyleg.com | https://indyleg.com | https://api.indyleg.com/metrics |

---

## 2. Monitoring

### Prometheus Metrics

Available at `GET /metrics` (Prometheus text format) and `GET /metrics/json` (JSON).

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by endpoint, method, status |
| `http_request_duration_seconds` | Histogram | Request latency by endpoint |
| `rate_limit_hits_total` | Counter | Rate limit rejections |
| `agent_runs_total` | Counter | Agent executions by agent_name, success/fail |
| `agent_run_duration_seconds` | Histogram | Agent execution time |
| `ingestion_documents_total` | Counter | Documents ingested |
| `ingestion_errors_total` | Counter | Ingestion failures |

### Key Alerts (Configure in Prometheus/CloudWatch)

| Alert | Condition | Severity | Action |
|---|---|---|---|
| High Error Rate | 5xx rate > 5% for 5 min | Critical | Check API logs, Bedrock status |
| High Latency | p95 > 5s for 10 min | Warning | Check DB connections, Bedrock throttling |
| Rate Limit Spike | rate_limit_hits > 100/min | Warning | Check for abuse; adjust RPM |
| Worker Queue Depth | SQS messages > 1000 | Warning | Scale workers; check DLQ |
| DLQ Non-Empty | DLQ messages > 0 | Warning | Investigate failed ingestions |
| Disk Usage | Aurora storage > 80% | Warning | Review data retention; scale storage |
| Redis Down | Connection failures | Warning | Rate limiting falls back to in-memory |

### Log Locations

| Component | Location | Format |
|---|---|---|
| API Server | CloudWatch `/ecs/indyleg-api` | JSON (structlog) |
| Worker | CloudWatch `/ecs/indyleg-worker` | JSON (structlog) |
| ALB | S3 `indyleg-alb-logs/` | GZIP |
| Local (all) | stdout | Pretty text |

### Useful Log Queries (CloudWatch Insights)

```sql
-- Recent errors
fields @timestamp, event, error, path
| filter level = "error"
| sort @timestamp desc
| limit 20

-- Slow requests (>3s)
fields @timestamp, path, latency_ms, user_id
| filter latency_ms > 3000
| sort latency_ms desc
| limit 20

-- Rate limited requests
fields @timestamp, client_ip, path
| filter event = "rate_limited"
| stats count() by client_ip
| sort count() desc

-- Agent failures
fields @timestamp, agent_name, error
| filter event = "agent_run" and success = false
| sort @timestamp desc
```

---

## 3. Health Checks

### API Health

```bash
curl -s http://localhost:8000/health | python -m json.tool
```

Expected response:
```json
{
    "status": "ok",
    "version": "0.2.0",
    "timestamp": "2026-04-15T14:30:00Z"
}
```

### Database Connectivity

```bash
# PostgreSQL
docker compose exec postgres pg_isready -U indyleg
# Expected: accepting connections

# Check vector extension
docker compose exec postgres psql -U indyleg -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
```

### OpenSearch Health

```bash
curl -s http://localhost:9200/_cluster/health | python -m json.tool
# Expected: {"status": "green", ...}

# Check index exists
curl -s http://localhost:9200/_cat/indices
```

### SQS Queue Status

```bash
# Local (LocalStack)
aws --endpoint-url http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/indyleg-ingestion \
  --attribute-names All

# AWS
aws sqs get-queue-attributes \
  --queue-url $SQS_INGESTION_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

### Redis Connectivity

```bash
redis-cli -u redis://localhost:6379 ping
# Expected: PONG
```

---

## 4. Common Issues & Resolutions

### 4.1 API Returns 500 Internal Server Error

**Symptoms**: 500 responses on API endpoints
**Diagnosis**:
```bash
# Check recent error logs
docker compose logs api --tail 50 --no-log-prefix | grep -i error

# Check database connectivity
curl http://localhost:8000/health
```
**Possible Causes & Fixes**:
| Cause | Fix |
|---|---|
| Database connection pool exhausted | Restart API: `docker compose restart api` |
| OpenSearch unreachable | Check: `curl http://localhost:9200` → restart if needed |
| Bedrock API error | Check AWS Bedrock status; verify IAM permissions |
| Invalid configuration | Verify `.env` file; check `docker compose config` |

---

### 4.2 Search Returning Empty Results

**Symptoms**: POST `/search` returns `{"results": []}`
**Diagnosis**:
```bash
# Check if documents are indexed
docker compose exec postgres psql -U indyleg -c "SELECT count(*) FROM legal_chunks;"

# Check OpenSearch
curl http://localhost:9200/legal_chunks/_count

# Check embeddings exist
docker compose exec postgres psql -U indyleg -c \
  "SELECT count(*) FROM legal_chunks WHERE embedding IS NOT NULL;"
```
**Fixes**:
| Cause | Fix |
|---|---|
| No documents ingested | Run: `make ingest-recent` |
| Embeddings are NULL | Re-run ingestion; check Bedrock connectivity |
| OpenSearch not indexed | Reindex from PostgreSQL |

---

### 4.3 Ingestion Worker Not Processing

**Symptoms**: SQS messages accumulating, no documents ingested
**Diagnosis**:
```bash
# Check worker logs
docker compose logs worker --tail 50

# Check SQS queue depth
aws --endpoint-url http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/indyleg-ingestion \
  --attribute-names ApproximateNumberOfMessages

# Check DLQ for failed messages
aws --endpoint-url http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/indyleg-ingestion-dlq \
  --attribute-names ApproximateNumberOfMessages
```
**Fixes**:
| Cause | Fix |
|---|---|
| Worker crashed | `docker compose restart worker` |
| SQS permission error | Check IAM role / LocalStack config |
| Bedrock throttling | Wait and retry; check Bedrock service quotas |
| DLQ filling up | Inspect DLQ messages; fix root cause; requeue |

---

### 4.4 Rate Limiting Issues

**Symptoms**: 429 Too Many Requests errors
**Diagnosis**:
```bash
# Check current rate limit config
grep RATE_LIMIT_RPM .env

# Check Redis connectivity
redis-cli ping

# Check metrics
curl http://localhost:8000/metrics/json | python -m json.tool
```
**Fixes**:
| Cause | Fix |
|---|---|
| Legitimate high traffic | Increase `RATE_LIMIT_RPM` |
| Redis down (using fallback) | Restart Redis; fallback is working but less accurate |
| Single client abusing | Block at ALB/WAF level |

---

### 4.5 Token/Auth Failures

**Symptoms**: 401 Unauthorized on valid tokens
**Diagnosis**:
```bash
# Decode a JWT (don't do in production with real tokens)
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | python -m json.tool

# Check if token is revoked
redis-cli -u redis://localhost:6379 SISMEMBER revoked_tokens "$TOKEN_JTI"
```
**Fixes**:
| Cause | Fix |
|---|---|
| Token expired | Re-authenticate via POST `/auth/token` |
| Token revoked | Issue new token |
| JWT_SECRET_KEY changed | All existing tokens invalid; users must re-login |
| Clock skew | Sync system clock (NTP) |

---

## 5. Incident Response

### Severity Levels

| Level | Description | Response Time | Examples |
|---|---|---|---|
| **SEV-1** | Complete service outage | 15 min | API down, database unreachable |
| **SEV-2** | Degraded service | 1 hour | Slow responses, partial failures |
| **SEV-3** | Minor issue | 4 hours | Single endpoint error, non-critical feature broken |
| **SEV-4** | Cosmetic / low impact | Next business day | UI glitch, log formatting |

### Incident Procedure

```text
1. DETECT    — Alert fires or user reports issue
2. ASSESS    — Determine severity level
3. COMMUNICATE — Notify stakeholders
4. DIAGNOSE  — Check logs, metrics, health endpoints
5. MITIGATE  — Apply quick fix (restart, rollback, scale)
6. RESOLVE   — Fix root cause
7. POSTMORTEM — Document: timeline, root cause, action items
```

### Quick Mitigation Actions

```bash
# Restart API service
docker compose restart api
# Or in AWS:
aws ecs update-service --cluster indyleg-prod --service indyleg-api --force-new-deployment

# Scale up workers
aws ecs update-service --cluster indyleg-prod --service indyleg-worker --desired-count 4

# Emergency: disable ingestion (purge SQS queue)
aws sqs purge-queue --queue-url $SQS_INGESTION_QUEUE_URL
```

---

## 6. Scaling

### Horizontal Scaling

| Component | How to Scale | Limit |
|---|---|---|
| API Server | Increase ECS task count | ALB handles routing |
| Ingestion Worker | Increase ECS task count | SQS parallel consumers |
| PostgreSQL | Aurora read replicas | Scale reads only |
| OpenSearch | Add data nodes | Horizontal scaling |
| Redis | ElastiCache cluster mode | Sharding |

### When to Scale

| Metric | Threshold | Action |
|---|---|---|
| API CPU | > 70% sustained | Add API tasks |
| API latency p95 | > 3 seconds | Add API tasks or check DB |
| SQS queue depth | > 500 messages | Add workers |
| DB connections | > 80% pool | Add read replicas |
| OpenSearch CPU | > 80% | Add data nodes |

### Scaling Commands

```bash
# Scale API to 4 tasks
aws ecs update-service --cluster indyleg-prod --service indyleg-api --desired-count 4

# Scale workers to 3
aws ecs update-service --cluster indyleg-prod --service indyleg-worker --desired-count 3
```

---

## 7. Backup & Recovery

### Automated Backups

| Component | Method | Retention | RPO |
|---|---|---|---|
| Aurora PostgreSQL | Automated snapshots | 7 days | 5 min (continuous backup) |
| OpenSearch | Automated snapshots | 14 days | 1 hour |
| S3 | Versioning enabled | Indefinite | 0 (immediate) |
| Redis | No backup (ephemeral) | — | Data reconstructible |

### Manual Backup

```bash
# PostgreSQL manual snapshot
aws rds create-db-cluster-snapshot \
  --db-cluster-identifier indyleg-prod \
  --db-cluster-snapshot-identifier indyleg-manual-$(date +%Y%m%d)

# OpenSearch manual snapshot
curl -X PUT "https://{opensearch}/_snapshot/manual/$(date +%Y%m%d)"
```

### Recovery Procedures

```bash
# Restore PostgreSQL to point in time
aws rds restore-db-cluster-to-point-in-time \
  --source-db-cluster-identifier indyleg-prod \
  --db-cluster-identifier indyleg-restore \
  --restore-to-time "2026-04-15T14:00:00Z"

# Restore from snapshot
aws rds restore-db-cluster-from-snapshot \
  --db-cluster-identifier indyleg-restore \
  --snapshot-identifier indyleg-manual-20260415
```

### Redis Recovery
Redis stores ephemeral data (rate limits, token blacklist). On failure:
- Rate limiting falls back to in-memory (automatic)
- Token blacklist is lost — tokens valid until natural expiry
- No data migration needed — Redis auto-populates on use

---

## 8. Operational Tasks

### 8.1 Ingest New Documents

```bash
# Recent filings (last 7 days, Marion County)
make ingest-recent

# Search and ingest by keyword
make ingest-search QUERY="eviction"

# Specific case
make ingest-case CASE="49D01-2401-CT-000123"

# Preview (dry run)
make ingest-dry
```

### 8.2 Reindex After Schema Change

```bash
# 1. Stop worker
docker compose stop worker

# 2. Apply schema changes
docker compose exec postgres psql -U indyleg -f /path/to/migration.sql

# 3. Rebuild IVFFLAT index (if embeddings changed)
docker compose exec postgres psql -U indyleg -c \
  "REINDEX INDEX legal_chunks_embedding_idx;"

# 4. Restart worker
docker compose start worker
```

### 8.3 Rotate JWT Secret Key

```bash
# 1. Generate new key
NEW_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Update in SSM
aws ssm put-parameter \
  --name "/indyleg/production/jwt_secret_key" \
  --value "$NEW_KEY" \
  --type SecureString \
  --overwrite

# 3. Restart API (all existing tokens become invalid)
aws ecs update-service --cluster indyleg-prod --service indyleg-api --force-new-deployment

# 4. Notify users to re-authenticate
```

### 8.4 Purge Dead Letter Queue

```bash
# 1. Inspect DLQ messages
aws sqs receive-message \
  --queue-url $DLQ_URL \
  --max-number-of-messages 10

# 2. If messages are safe to discard
aws sqs purge-queue --queue-url $DLQ_URL

# 3. If messages should be reprocessed — move back to main queue
# (use SQS DLQ redrive feature in AWS Console)
```

### 8.5 Revoke a User's Tokens

```bash
# Admin endpoint
curl -X POST https://api.indyleg.com/auth/revoke \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"token": "USER_TOKEN_TO_REVOKE"}'
```

---

## 9. Contacts & Escalation

| Role | Responsibility | Contact |
|---|---|---|
| On-Call Engineer | First responder for alerts | PagerDuty / Slack #indyleg-oncall |
| Backend Lead | API, agents, retrieval pipeline | — |
| Infrastructure Lead | CDK, AWS resources, networking | — |
| Security Lead | Auth, rate limiting, incident response | — |

### Escalation Path

```text
Alert → On-Call Engineer (15 min) → Backend/Infra Lead (30 min) → Management (1 hour)
```
