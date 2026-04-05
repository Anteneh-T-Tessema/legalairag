# IndyLeg Architecture Guide

This document provides a detailed technical overview of the IndyLeg architecture for developers and system administrators.

---

## System Layers

IndyLeg follows a layered architecture with clear separation of concerns:

```text
┌──────────────────────────────────────────────────┐
│                 Presentation Layer                │
│  React UI (Vite + TypeScript)                    │
│  FastAPI REST endpoints (/api/v1/*)              │
├──────────────────────────────────────────────────┤
│                 Agent Layer                       │
│  CaseResearchAgent   (5-step RAG pipeline)       │
│  SummarizationAgent  (structured extraction)     │
│  FraudDetectionAgent (pattern analysis)          │
│  BaseAgent           (audit trail, tool control) │
├──────────────────────────────────────────────────┤
│                 Retrieval Layer                   │
│  QueryParser → Embedder → HybridSearch           │
│  AuthorityRanker → CitationGraph                 │
│  CrossEncoder Reranker                           │
├──────────────────────────────────────────────────┤
│                 Generation Layer                  │
│  Bedrock Claude 3.5 Sonnet (temp=0.0)            │
│  Citation Validator (hallucination guard)         │
├──────────────────────────────────────────────────┤
│                 Ingestion Layer                   │
│  Indiana Courts API + Public Data Sources        │
│  SQS Queue → Worker Pool → Chunker → Embedder   │
├──────────────────────────────────────────────────┤
│                 Infrastructure                    │
│  Aurora PostgreSQL + pgvector                    │
│  OpenSearch (BM25)                               │
│  S3 (raw + processed documents)                  │
│  SQS + DLQ (message queues)                     │
│  ECS Fargate (compute)                           │
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
- **Authorization**: Role-based (Admin/Attorney/Clerk/Viewer) checked via `require_role()` decorator
- **Password storage**: HMAC-SHA256 with 32-byte random salt — no plaintext storage
- **Audit logging**: `AuditLogMiddleware` logs all API requests with redacted auth headers
- **CORS**: Explicit origin allowlist (not `*`); Swagger UI disabled in production
- **Agent auditing**: Every agent execution logged with `run_id` for full traceability

---

## Database Design

### PostgreSQL (pgvector)

| Table | Purpose |
|---|---|
| `legal_chunks` | Document chunks with 1024-dim embeddings + JSONB metadata |
| `document_versions` | Content-hash dedup for ingestion |
| `citation_edges` | Citation relationships between opinions |

HNSW index (`ef_construction=128, m=16`) for approximate nearest neighbor search. GIN index on metadata JSONB for filtered queries.

### OpenSearch

Single index `indyleg-legal-docs` with BM25 scoring. Custom `legal_analyzer` with standard tokenizer + lowercase + stop filter. Keyword fields for structured filtering (jurisdiction, case_type, citations).

---

## Infrastructure (AWS)

| Service | Purpose | Configuration |
|---|---|---|
| ECS Fargate | API + Worker compute | 2-6 tasks, CPU auto-scaling at 70% |
| Aurora PostgreSQL | Primary data store + pgvector | Multi-AZ, pgvector extension |
| OpenSearch | BM25 keyword search | 2 data nodes, t3.medium.search |
| S3 | Document storage | raw + processed buckets, versioned |
| SQS | Ingestion queues | FIFO + DLQ, 3 retries, 5-min visibility |
| Bedrock | LLM + Embeddings | Claude 3.5 Sonnet + Titan Embed v2 |
| ALB | Load balancer | Public-facing, routes to ECS |

All resources deployed via AWS CDK in three stacks: Network, Data, API.
