# IndyLeg Architecture Guide

This document provides a detailed technical overview of the IndyLeg platform — an AI-powered legal research and fraud detection system built for Indiana courts.

**Version**: 0.7.0 | **Last Updated**: April 2026

---

## Table of Contents

- [System Overview](#system-overview)
- [System Layers](#system-layers)
- [Data Flow](#data-flow)
- [Module Map](#module-map)
- [Agent Framework](#agent-framework)
- [Retrieval Pipeline](#retrieval-pipeline)
- [Authority & Citation System](#authority--citation-system)
- [Generation & Validation](#generation--validation)
- [Ingestion Pipeline](#ingestion-pipeline)
- [Security Model](#security-model)
- [Observability](#observability)
- [Database Design](#database-design)
- [Infrastructure](#infrastructure-aws)
- [Technology Stack](#technology-stack)

---

## System Overview

IndyLeg is a Retrieval-Augmented Generation (RAG) platform for Indiana legal research. It ingests court filings, statutes, and public legal opinions, stores them as vector embeddings, and answers legal questions with citation-grounded responses. A fraud detection subsystem analyzes filing patterns for anomalies.

```text
┌─────────────────┐     ┌───────────────┐     ┌─────────────────┐
│  Indiana Courts  │     │ CourtListener │     │ law.resource.org│
│  API (Odyssey)   │     │ (Free Law)    │     │ (7th Circuit)   │
└────────┬────────┘     └───────┬───────┘     └────────┬────────┘
         │                      │                       │
         └──────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Ingestion Pipeline  │
                    │  SQS → Worker → Chunk │
                    │  → Embed → pgvector   │
                    └───────────┬───────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                       │
  ┌──────▼──────┐     ┌────────▼────────┐     ┌───────▼───────┐
  │  pgvector   │     │   OpenSearch    │     │      S3       │
  │  (vectors)  │     │    (BM25)       │     │   (raw docs)  │
  └──────┬──────┘     └────────┬────────┘     └───────────────┘
         │                      │
         └──────────┬───────────┘
                    │
          ┌─────────▼──────────┐
          │  Hybrid Retrieval  │
          │  RRF → Rerank →    │
          │  Authority Rank    │
          └─────────┬──────────┘
                    │
          ┌─────────▼──────────┐
          │  Agent Framework   │
          │  Research │ Fraud  │
          │  Summary  │ Base   │
          └─────────┬──────────┘
                    │
          ┌─────────▼──────────┐
          │ FastAPI + React UI │
          │ Auth │ Audit │ Rate│
          └────────────────────┘
```

---

## System Layers

```text
┌──────────────────────────────────────────────────┐
│                 Presentation Layer                │
│  React 18 UI (Vite + TypeScript)                 │
│  FastAPI REST endpoints (/api/v1/*)              │
│  Prometheus /metrics + JSON /metrics/json        │
├──────────────────────────────────────────────────┤
│               Middleware Layer                    │
│  SecurityHeaders → RateLimit (Redis/in-memory)   │
│  AuditLog (structlog JSON) → Metrics             │
│  CORS → JWT Authentication (HS256)               │
├──────────────────────────────────────────────────┤
│                 Agent Layer                       │
│  CaseResearchAgent   (6-step RAG pipeline)       │
│  SummarizationAgent  (structured extraction)     │
│  FraudDetectionAgent (5 pattern detectors)       │
│  BaseAgent           (audit trail, tool control) │
├──────────────────────────────────────────────────┤
│                 Retrieval Layer                   │
│  QueryParser → Embedder → HybridSearch (RRF)     │
│  AuthorityRanker → CitationGraph (PageRank)      │
│  CrossEncoder Reranker (ms-marco-MiniLM)         │
├──────────────────────────────────────────────────┤
│                 Generation Layer                  │
│  Bedrock Claude 3.5 Sonnet (temp=0.0)            │
│  Citation Validator (hallucination guard)         │
│  Legal QA / Summarization / Research prompts     │
├──────────────────────────────────────────────────┤
│                 Ingestion Layer                   │
│  Indiana Courts API + CourtListener + IGA        │
│  law.resource.org (7th Circuit bulk)             │
│  SQS Queue → Worker → Chunker → Embedder        │
├──────────────────────────────────────────────────┤
│                 Infrastructure                    │
│  Aurora PostgreSQL + pgvector (vectors)           │
│  OpenSearch (BM25 keyword search)                │
│  S3 (raw + processed documents)                  │
│  SQS + DLQ (ingestion queues)                   │
│  ElastiCache Redis (rate limits, token revoke)   │
│  ECS Fargate (compute) behind ALB               │
│  AWS Bedrock (Claude 3.5 + Titan Embed v2)      │
└──────────────────────────────────────────────────┘
```

---

## Data Flow

### Ingestion Path

1. **Discovery**: Indiana Courts API client discovers new filings; public source clients (CourtListener, law.resource.org, IGA) fetch opinions and statutes
2. **Queuing**: Documents are enqueued to SQS as `IngestionMessage` records
3. **Deduplication**: Worker checks `document_versions` table via content hash — skips duplicates
4. **Processing**: Worker downloads → parses → chunks (legal-aware boundaries) → embeds (Titan v2)
5. **Storage**: Vectors stored in pgvector, keywords indexed in OpenSearch, raw docs in S3

### Query Path

1. **Parsing**: `QueryParser` extracts jurisdiction, case type, Indiana Code citations, BM25 keywords
2. **Embedding**: Query text embedded via Bedrock Titan Embed v2 (1024-dim)
3. **Retrieval**: Dual retrieval — pgvector cosine similarity + OpenSearch BM25 — fused via RRF (k=60)
4. **Authority Reranking**: `AuthorityRanker` blends retrieval scores with court hierarchy weights
5. **Cross-Encoder Reranking**: ms-marco-MiniLM-L-6-v2 rescores top candidates
6. **Generation**: Claude 3.5 Sonnet generates answer with `[SOURCE: id]` citations
7. **Validation**: `CitationValidator` verifies every citation maps to a retrieved chunk

---

## Agent Framework

All agents inherit from `BaseAgent`, which enforces:

- **Audit trail**: Every execution creates an `AgentRun` record with a UUID `run_id`
- **Tool access control**: Agents declare `allowed_tools` — calling an unlisted tool raises `PermissionError`
- **Structured logging**: Every tool call is recorded with timestamp and inputs
- **Error handling**: Failures persist the error in the audit record for post-mortem analysis

### Agent Inventory

| Agent | Tools | Purpose |
|---|---|---|
| `CaseResearchAgent` | query_parse, embed, search, rerank, generate | Full RAG pipeline with authority reranking |
| `SummarizationAgent` | query_parse, embed, search, summarize | Structured case document summarization |
| `FraudDetectionAgent` | query_parse, embed, search, analyze_patterns, generate_summary | Fraud pattern detection and investigation memo generation |

---

## Authority & Citation System

### Court Hierarchy

The `AuthorityRanker` implements Indiana's court precedent hierarchy:

```text
US Supreme Court            → 1.00 (binding on federal questions)
7th Circuit                 → 0.90 (binding federal circuit for Indiana)
Indiana Supreme Court       → 0.85 (highest state authority)
Indiana Court of Appeals    → 0.70 (binding unless overruled)
Indiana Tax Court           → 0.60 (tax matters only)
Federal District (S.D./N.D. Ind.) → 0.55 (persuasive)
Indiana Trial Courts        → 0.40 (persuasive only)
```

### Citation Graph

The `CitationGraph` maintains citation relationships between opinions:

- **Good-law validation**: Opinions with `overruled` or `reversed` treatment are flagged
- **PageRank**: Iterative authority propagation — widely-cited opinions score higher
- **Precedent traversal**: BFS walks the citation tree to find all precedents at configurable depth
- **Result enrichment**: Filters bad-law results and boosts PageRank-scored opinions

---

## Security Model

- **Authentication**: JWT (HS256) with 60-min access tokens and 7-day refresh tokens
- **Token Rotation**: Refresh tokens are revoked on use (rotation prevents replay)
- **Token Revocation**: Blacklist backed by Redis (with TTL) or in-memory fallback; revoke via `POST /auth/revoke`
- **Authorization**: Role-based (Admin/Attorney/Clerk/Viewer) checked via `require_role()` decorator
- **Password storage**: HMAC-SHA256 with 32-byte random salt — constant-time comparison via `hmac.compare_digest`
- **Rate Limiting**: Per-IP sliding window — Redis (production) with in-memory token bucket fallback (dev)
- **Audit logging**: `AuditLogMiddleware` logs all API requests with unique `X-Request-Id` and redacted auth headers
- **Security headers**: OWASP-recommended (X-Content-Type-Options, X-Frame-Options, CSP, HSTS on HTTPS)
- **CORS**: Explicit origin allowlist (not `*`); Swagger UI disabled in production
- **Secrets management**: SSM Parameter Store + Secrets Manager with cascading resolution and LRU cache
- **Agent auditing**: Every agent execution logged with `run_id` for full traceability

---

## Observability

### Metrics

The `/metrics` endpoint exposes Prometheus-format metrics:
- `http_requests_total{method, path}` — request count per route
- `http_errors_total{method, path}` — 5xx error count
- `http_request_duration_ms{method, path, quantile}` — latency percentiles (p50, p95, p99)

The `/metrics/json` endpoint exposes the same data as a JSON dict for dashboards.

### Structured Logging

All logs emitted as structured JSON via `structlog`:
- Every request tagged with a unique `request_id`
- Agent runs tagged with `run_id`
- Tool calls logged with timestamp and inputs

### Health Check

`GET /health` returns `{"status": "ok", "env": "..."}` — no authentication required.

---

## Database Design

### PostgreSQL (pgvector)

| Table | Purpose |
|---|---|
| `legal_chunks` | Document chunks with 1024-dim embeddings + JSONB metadata |
| `document_versions` | Content-hash dedup for ingestion |
| `citation_edges` | Citation relationships between opinions |

IVFFlat index (`lists=100, vector_cosine_ops`) for approximate nearest neighbor search. GIN index on metadata JSONB for filtered queries.

### OpenSearch

Single index `indyleg-legal-docs` with BM25 scoring. Custom `legal_analyzer` with standard tokenizer + lowercase + stop filter. Keyword fields for structured filtering (jurisdiction, case_type, citations).

---

## Infrastructure (AWS)

| Service | Purpose | Configuration |
|---|---|---|
| ECS Fargate | API + Worker compute | 2-6 tasks, CPU auto-scaling at 70% |
| Aurora PostgreSQL | Primary data store + pgvector | Multi-AZ, r6g.large, v16.2 |
| OpenSearch | BM25 keyword search | 2 data nodes, r6g.large, 100 GiB |
| S3 | Document storage | raw (versioned) + processed buckets |
| SQS | Ingestion queues | 5-min visibility + DLQ (3 retries, 14-day retention) |
| Bedrock | LLM + Embeddings | Claude 3.5 Sonnet + Titan Embed v2 |
| ALB | Load balancer | Public-facing, health-checked, routes to ECS |
| ElastiCache Redis | Rate limiting + token revocation | Sliding window counters, key-TTL revocation |
| SSM Parameter Store | Secrets management | Production secret overlay |

All resources deployed via AWS CDK in three stacks:

| Stack | Resources |
|---|---|
| `RetrievalStack` | VPC (2 AZs), Aurora PostgreSQL, OpenSearch |
| `IngestionStack` | S3 buckets, SQS queues + DLQ, Fargate worker (2048 CPU, 4 GiB) |
| `ApiStack` | ALB, Fargate API service (1024 CPU, 2 GiB), auto-scaling |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript 5.4, Vite 5.3 |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| LLM | AWS Bedrock — Claude 3.5 Sonnet (generation), Titan Embed v2 (embeddings) |
| Vector DB | PostgreSQL 16 + pgvector (IVFFLAT, 1024-dim) |
| Keyword Search | OpenSearch 2.14 (BM25) |
| Reranking | sentence-transformers ms-marco-MiniLM-L-6-v2 |
| Auth | PyJWT (HS256), RBAC, token revocation |
| Queue | Amazon SQS + DLQ |
| Storage | Amazon S3 |
| Cache/Rate Limit | Redis (ElastiCache) |
| Observability | structlog (JSON), Prometheus metrics |
| IaC | AWS CDK (Python) |
| CI/CD | GitHub Actions |
| Testing | pytest (Python), Vitest + React Testing Library (UI) |
| Linting | ruff (Python), TypeScript strict mode |
