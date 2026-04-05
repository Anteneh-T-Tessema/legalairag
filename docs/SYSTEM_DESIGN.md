# System Design Document

**Project**: IndyLeg — Indiana Legal AI RAG Platform
**Version**: 0.2.0 | **Date**: April 2026

---

## Table of Contents

- [1. Design Philosophy](#1-design-philosophy)
- [2. High-Level Architecture](#2-high-level-architecture)
- [3. Component Design](#3-component-design)
- [4. Module Interactions](#4-module-interactions)
- [5. Sequence Diagrams](#5-sequence-diagrams)
- [6. Design Patterns](#6-design-patterns)
- [7. Interface Specifications](#7-interface-specifications)
- [8. Error Handling Strategy](#8-error-handling-strategy)
- [9. Configuration Management](#9-configuration-management)

---

## 1. Design Philosophy

| Principle | Application |
|---|---|
| **Modular Layering** | Six isolated layers (API → Agents → Retrieval → Generation → Ingestion → Infrastructure) with clean interfaces |
| **Fail-Safe Generation** | LLM outputs validated before delivery; hallucinations rejected with fallback responses |
| **Domain-Driven** | Legal domain concepts (court hierarchy, authority, citations) first-class in the retrieval pipeline |
| **Async-First** | All I/O-bound operations use `async/await`; SQS decouples ingestion from serving |
| **Progressive Degradation** | Redis unavailable → in-memory fallback; Bedrock timeout → cached response; source down → alternate source |
| **Zero-Trust Security** | JWT validation on every request, RBAC enforcement, audit logging, token revocation |

---

## 2. High-Level Architecture

```mermaid
graph TB
    subgraph "Presentation Layer"
        UI[React SPA<br/>Vite + TypeScript]
        UI --> |HTTPS REST| API
    end

    subgraph "API Layer"
        API[FastAPI v0.2.0]
        MW[Middleware Stack<br/>Security → Rate Limit → Audit → Metrics]
        API --> MW
        MW --> R1[auth_router]
        MW --> R2[search_router]
        MW --> R3[fraud_router]
        MW --> R4[documents_router]
    end

    subgraph "Agent Layer"
        BA[BaseAgent ABC]
        RA[CaseResearchAgent]
        FA[FraudDetectionAgent]
        SA[SummarizationAgent]
        BA --> RA
        BA --> FA
        BA --> SA
    end

    subgraph "Retrieval Layer"
        QP[QueryParser]
        HS[HybridSearcher]
        CR[CrossEncoderReranker]
        AR[AuthorityRanker]
        QP --> HS --> CR --> AR
    end

    subgraph "Generation Layer"
        LG[LegalGenerator]
        CV[CitationValidator]
        BC[BedrockLLMClient]
        LG --> CV
        LG --> BC
    end

    subgraph "Ingestion Layer"
        SRC[Document Sources]
        WK[IngestionWorker]
        CH[LegalChunker]
        EM[BedrockEmbedder]
        SRC --> WK --> CH --> EM
    end

    subgraph "Storage Layer"
        PG[(PostgreSQL<br/>pgvector)]
        OS[(OpenSearch<br/>BM25)]
        S3[(S3<br/>Raw docs)]
        RD[(Redis<br/>Cache + Revoke)]
        SQS[SQS<br/>Queue + DLQ]
    end

    R2 --> RA
    R3 --> FA
    R4 --> WK
    RA --> QP
    RA --> LG
    FA --> HS
    HS --> PG
    HS --> OS
    EM --> PG
    WK --> SQS
    WK --> S3
    BC --> BED[AWS Bedrock<br/>Claude 3.5 Sonnet]
    EM --> BED2[AWS Bedrock<br/>Titan Embed v2]
    API --> RD
```

---

## 3. Component Design

### 3.1 API Layer

**Module**: `api/`

The API layer is a FastAPI application that exposes all system functionality over REST.

#### Middleware Stack (order matters)

```text
Request → SecurityHeaders → RateLimiter → AuditLogger → MetricsCollector → CORS → Router
```

| Middleware | Responsibility | Key Details |
|---|---|---|
| `SecurityHeaders` | Inject security headers (CSP, HSTS, X-Frame-Options) | Applied to every response |
| `RateLimiter` | Sliding window rate limiting | Redis primary, in-memory token bucket fallback |
| `AuditLogger` | Structured request/response logging | structlog JSON, includes user_id if authenticated |
| `MetricsCollector` | Prometheus counter/histogram collection | Request count, latency by endpoint + method |
| `CORSMiddleware` | Cross-origin policy | Configurable allowed_origins |

#### Routers

| Router | Prefix | Key Endpoints |
|---|---|---|
| `auth_router` | `/auth` | POST `/token`, `/refresh`, `/logout`, `/revoke`; GET `/me` |
| `search` | `/search` | POST `/search`, POST `/search/ask` |
| `fraud` | `/fraud` | POST `/fraud/analyze` |
| `documents` | `/documents` | POST `/documents/ingest` (ADMIN/ATTORNEY) |

### 3.2 Agent Layer

**Module**: `agents/`

#### Class Hierarchy

```mermaid
classDiagram
    class BaseAgent {
        <<abstract>>
        +name: str
        +allowed_tools: list[str]
        +run(input) AgentRun*
        -_validate_tool_access(tool: str)
        -_create_audit_trail() AgentRun
    }

    class AgentRun {
        +agent_name: str
        +input: str
        +output: str
        +steps: list[str]
        +tools_used: list[str]
        +started_at: datetime
        +completed_at: datetime
        +success: bool
        +error: str | None
    }

    class CaseResearchAgent {
        +name = "case_research"
        +allowed_tools = ["search", "embed", "generate"]
        +run(query) AgentRun
        -_parse_query()
        -_embed_query()
        -_hybrid_search()
        -_temporal_filter()
        -_rerank()
        -_authority_blend()
        -_generate_answer()
        -_estimate_confidence()
    }

    class FraudDetectionAgent {
        +name = "fraud_detection"
        +allowed_tools = ["search"]
        +run(query) AgentRun
        -_retrieve_candidates()
        -_detect_burst_filing()
        -_detect_identity_reuse()
        -_detect_deed_fraud()
        -_detect_suspicious_entities()
        -_detect_rapid_ownership()
        -_compute_risk_level()
    }

    class SummarizationAgent {
        +name = "summarization"
        +allowed_tools = ["generate"]
        +run(document) AgentRun
        -_parse_document()
        -_summarize()
        -_extract_entities()
    }

    BaseAgent <|-- CaseResearchAgent
    BaseAgent <|-- FraudDetectionAgent
    BaseAgent <|-- SummarizationAgent
    BaseAgent --> AgentRun
```

### 3.3 Retrieval Layer

**Module**: `retrieval/`

#### Pipeline Components

| Component | Class | Responsibility |
|---|---|---|
| Query Parser | `QueryParser` | Extracts jurisdiction, case_type, citations; classifies query type; sets adaptive weights |
| Hybrid Searcher | `HybridSearcher` | Runs cosine + BM25 in parallel; fuses via RRF (k=60) |
| Cross-Encoder | `CrossEncoderReranker` | Joint passage-query scoring with ms-marco-MiniLM-L-6-v2 |
| Authority Ranker | `AuthorityRanker` | Court hierarchy weighting; citation graph PageRank |
| RAG Evaluator | `RAGEvaluator` | Offline metrics: recall@K, precision@K, MRR, NDCG |
| Vector Indexer | `VectorIndexer` | PostgreSQL schema management; IVFFLAT index creation |

#### Authority Score Weights

```text
Court Level           Weight    Examples
──────────────────────────────────────────────
US Supreme Court      1.00     Brown v. Board
US Circuit Court      0.90     7th Circuit opinions
Indiana Supreme       0.85     State high court
Indiana Appeals       0.75     Intermediate appellate
IN Tax / Workers Comp 0.65     Specialty courts
Trial Court           0.40     County-level
Default               0.35     Unrecognized courts
```

**Blending Formula**: `final_score = (1 - α) × retrieval_score + α × authority_score`

Where α is adaptively set by the QueryParser (higher for citation-heavy queries).

### 3.4 Generation Layer

**Module**: `generation/`

| Component | Responsibility |
|---|---|
| `LegalGenerator` | Builds prompts from templates → invokes Claude → validates output |
| `CitationValidator` | Extracts `[SOURCE: id]` markers → verifies each maps to retrieved chunk |
| `BedrockLLMClient` | Thin wrapper around Bedrock Converse API; retries (max 3) |
| `prompts/legal_qa.py` | Prompt templates: legal_qa, summarization, case_research |

**Generation Contract**: Every answer must include `[SOURCE: chunk_id]` citations. Any ungrounded citation triggers fallback.

### 3.5 Ingestion Layer

**Module**: `ingestion/`

| Component | Responsibility |
|---|---|
| `IngestionWorker` | Orchestrates: SQS poll → download → parse → dedup → chunk → embed → store |
| `LegalChunker` | Structure-aware splitting at SECTION/ARTICLE boundaries; max 512 tokens, 64 overlap |
| `BedrockEmbedder` | Batched embedding (128/batch, 4 concurrent) via Titan Embed v2 |
| `SQSProducer/Consumer` | Message queue integration with DLQ support |
| `IndianaCourtClient` | Odyssey API client with rate limiting (semaphore=5) |
| `DocumentLoader` | Format dispatcher: PDF → pdfplumber, DOCX → python-docx, HTML → BeautifulSoup |

### 3.6 Configuration Layer

**Module**: `config/`

| Component | Responsibility |
|---|---|
| `Settings` | Pydantic BaseSettings — single source of truth for all config |
| `SecretsResolver` | SSM Parameter Store → Secrets Manager → env vars (cascade) |
| `configure_logging` | structlog (JSON in prod, pretty in dev) |

---

## 4. Module Interactions

### Dependency Graph

```mermaid
graph LR
    API --> Agents
    API --> Config
    Agents --> Retrieval
    Agents --> Generation
    Retrieval --> Config
    Generation --> Config
    Ingestion --> Config
    Ingestion --> Retrieval

    style API fill:#4a90d9,color:#fff
    style Agents fill:#7b68ee,color:#fff
    style Retrieval fill:#50c878,color:#fff
    style Generation fill:#ff6b6b,color:#fff
    style Ingestion fill:#ffa500,color:#fff
    style Config fill:#808080,color:#fff
```

### Key Integration Points

| From | To | Interface | Data |
|---|---|---|---|
| `search_router` | `CaseResearchAgent.run()` | Async method | `SearchRequest` → `SearchResponse` |
| `fraud_router` | `FraudDetectionAgent.run()` | Async method | `FraudRequest` → `FraudAnalysisResult` |
| `CaseResearchAgent` | `HybridSearcher.search()` | Async method | `query_vector`, `text`, `filters` → `SearchResult[]` |
| `CaseResearchAgent` | `LegalGenerator.generate()` | Async method | `context`, `question` → `GeneratedAnswer` |
| `HybridSearcher` | PostgreSQL | SQL (asyncpg) | `SELECT ... ORDER BY embedding <=> $1` |
| `HybridSearcher` | OpenSearch | REST API | `{"query": {"match": ...}}` |
| `LegalGenerator` | `BedrockLLMClient.complete()` | Async method | Prompt → text response |
| `IngestionWorker` | `SQSConsumer.receive()` | Async method | → `IngestionMessage[]` |
| `IngestionWorker` | `VectorIndexer.upsert()` | Async method | Chunks + vectors → PostgreSQL |

---

## 5. Sequence Diagrams

### 5.1 Legal Question (RAG) Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as React UI
    participant API as FastAPI
    participant MW as Middleware
    participant RA as CaseResearchAgent
    participant QP as QueryParser
    participant HS as HybridSearcher
    participant PG as PostgreSQL
    participant OS as OpenSearch
    participant CR as CrossEncoder
    participant AR as AuthorityRanker
    participant GEN as LegalGenerator
    participant BED as Bedrock Claude
    participant VAL as Validator

    User->>UI: Enter question
    UI->>API: POST /search/ask
    API->>MW: SecurityHeaders → RateLimit → Audit → Metrics
    MW->>RA: run(query)

    RA->>QP: parse_legal_query(text)
    QP-->>RA: ParsedQuery (type, jurisdiction, weights)

    RA->>BED: embed(query)
    BED-->>RA: query_vector[1024]

    par Hybrid Search
        RA->>HS: search(query_vector, text)
        HS->>PG: cosine similarity search
        PG-->>HS: vector results
        HS->>OS: BM25 keyword search
        OS-->>HS: keyword results
        HS-->>RA: fused results (RRF k=60)
    end

    RA->>CR: rerank(query, results)
    CR-->>RA: reranked results

    RA->>AR: authority_blend(results, α)
    AR-->>RA: authority-ranked results

    RA->>GEN: generate(question, context)
    GEN->>BED: converse(prompt)
    BED-->>GEN: response with [SOURCE: id]

    GEN->>VAL: validate_citations(response, context)
    VAL-->>GEN: validation result

    alt Citations Valid
        GEN-->>RA: answer + sources
    else Hallucination Detected
        GEN-->>RA: fallback response
    end

    RA-->>API: AgentRun (answer, steps, confidence)
    API-->>UI: SearchResponse
    UI-->>User: Display answer + sources
```

### 5.2 Fraud Analysis Flow

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI
    participant FA as FraudDetectionAgent
    participant HS as HybridSearcher
    participant PG as PostgreSQL

    User->>API: POST /fraud/analyze
    API->>FA: run(query)

    FA->>HS: search(query, limit=50)
    HS->>PG: retrieve candidate filings
    PG-->>HS: 50 filings
    HS-->>FA: filings

    rect rgb(255, 235, 235)
        Note over FA: Fraud Detection Pipeline
        FA->>FA: detect_burst_filing(filings)
        FA->>FA: detect_identity_reuse(filings)
        FA->>FA: detect_deed_fraud(filings)
        FA->>FA: detect_suspicious_entities(filings)
        FA->>FA: detect_rapid_ownership(filings)
    end

    FA->>FA: compute_risk_level(indicators)
    FA->>FA: generate_advisory_memo()

    FA-->>API: FraudAnalysisResult
    API-->>User: Risk level + indicators + memo
```

### 5.3 Document Ingestion Flow

```mermaid
sequenceDiagram
    actor Admin
    participant API as FastAPI
    participant SQS as SQS Queue
    participant WK as IngestionWorker
    participant DL as DocumentLoader
    participant CH as LegalChunker
    participant EM as BedrockEmbedder
    participant PG as PostgreSQL
    participant OS as OpenSearch
    participant S3 as S3

    Admin->>API: POST /documents/ingest
    API->>SQS: send_message(IngestionMessage)
    API-->>Admin: 202 Accepted

    loop Poll Queue
        WK->>SQS: receive_messages()
        SQS-->>WK: IngestionMessage

        WK->>S3: download(source_url)
        S3-->>WK: raw bytes

        WK->>DL: load_from_bytes(bytes, format)
        DL-->>WK: parsed text

        WK->>PG: check content_hash
        alt Duplicate
            PG-->>WK: exists → skip
        else New Document
            PG-->>WK: new

            WK->>CH: chunk(text)
            CH-->>WK: Chunk[] (≤512 tokens)

            WK->>EM: embed_batch(chunks)
            EM-->>WK: vectors[1024][]

            par Store
                WK->>PG: upsert(chunks, vectors)
                WK->>OS: index(chunks, metadata)
            end
        end

        WK->>SQS: delete_message()
    end
```

### 5.4 Authentication Flow

```mermaid
sequenceDiagram
    actor User
    participant UI as React UI
    participant API as FastAPI
    participant AUTH as auth.py
    participant RED as Redis

    User->>UI: Enter credentials
    UI->>API: POST /auth/token
    API->>AUTH: verify_password(username, password)
    AUTH-->>API: user verified

    API->>AUTH: create_access_token(user, role)
    AUTH-->>API: access_token (60 min)

    API->>AUTH: create_refresh_token(user)
    AUTH-->>API: refresh_token (7 days)

    API-->>UI: {access_token, refresh_token}

    Note over UI: Token expires...

    UI->>API: POST /auth/refresh
    API->>AUTH: verify_refresh_token(token)
    AUTH->>RED: check revocation blacklist
    RED-->>AUTH: not revoked
    AUTH->>AUTH: create new access_token + rotate refresh_token
    AUTH->>RED: revoke old refresh_token
    AUTH-->>API: {new_access, new_refresh}
    API-->>UI: rotated tokens

    Note over User: Logout

    UI->>API: POST /auth/logout
    API->>AUTH: revoke_token(access_token)
    AUTH->>RED: add to blacklist (TTL = token remaining life)
    AUTH-->>API: success
    API-->>UI: 200 OK
```

---

## 6. Design Patterns

| Pattern | Where Used | Purpose |
|---|---|---|
| **Template Method** | `BaseAgent.run()` | Defines audit-trail skeleton; subclasses implement specific logic |
| **Strategy** | `QueryParser` → adaptive weights | Different retrieval strategies (citation_lookup vs. semantic vs. hybrid) |
| **Pipeline** | `CaseResearchAgent` 7-step chain | Sequential processing with intermediate results |
| **Observer** | `MetricsCollector` middleware | Non-intrusive request/response measurement |
| **Decorator** | `@require_role(...)` | Declarative RBAC enforcement on endpoints |
| **Factory** | `DocumentLoader.load_from_bytes()` | Format-specific parser selection (PDF/DOCX/HTML/TXT) |
| **Facade** | `HybridSearcher` | Unifies pgvector + OpenSearch behind single `search()` |
| **Circuit Breaker** | Redis rate limiter | Falls back to in-memory if Redis unavailable |
| **Chain of Responsibility** | Middleware stack | Request passes through sequential handlers |
| **Repository** | `VectorIndexer` | Abstracts storage behind `upsert()` / `search()` |
| **Producer/Consumer** | SQS ingestion queue | Decouples document submission from processing |
| **Cascade** | `SecretsResolver` | SSM → Secrets Manager → env var fallback |

---

## 7. Interface Specifications

### 7.1 Internal APIs

#### HybridSearcher

```python
class HybridSearcher:
    async def search(
        self,
        query_text: str,
        query_vector: list[float],  # 1024-dim
        *,
        jurisdiction: str | None = None,
        case_type: str | None = None,
        bm25_weight: float = 0.3,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Fused vector + keyword search with RRF."""
```

#### AuthorityRanker

```python
class AuthorityRanker:
    def authority_blend(
        self,
        results: list[SearchResult],
        alpha: float = 0.3,
    ) -> list[SearchResult]:
        """Re-rank by (1-α)×retrieval + α×authority."""
```

#### LegalGenerator

```python
class LegalGenerator:
    async def generate(
        self,
        question: str,
        context: list[SearchResult],
        *,
        prompt_type: str = "legal_qa",
    ) -> GeneratedAnswer:
        """Generate citation-grounded answer."""
```

#### FraudDetectionAgent

```python
class FraudDetectionAgent(BaseAgent):
    async def run(
        self,
        query: str,
    ) -> AgentRun:
        """Run 5 fraud detectors, return FraudAnalysisResult."""
```

### 7.2 External API (REST)

See [API.md](API.md) for complete endpoint specifications.

| Method | Path | Request Body | Response |
|---|---|---|---|
| POST | `/auth/token` | `{username, password}` | `{access_token, refresh_token}` |
| POST | `/auth/refresh` | `{refresh_token}` | `{access_token, refresh_token}` |
| POST | `/auth/logout` | — (Bearer token) | `{message}` |
| POST | `/auth/revoke` | `{token}` (Admin only) | `{message}` |
| GET | `/auth/me` | — | `{username, role, ...}` |
| POST | `/search` | `{query, jurisdiction?, case_type?, top_k?}` | `{results: SearchResult[]}` |
| POST | `/search/ask` | `{query, jurisdiction?, case_type?}` | `{answer, sources, confidence}` |
| POST | `/fraud/analyze` | `{query, analysis_type?}` | `{risk_level, indicators, memo}` |
| POST | `/documents/ingest` | `{source_url, document_type, metadata}` | `{message, ingestion_id}` |
| GET | `/health` | — | `{status, version, timestamp}` |
| GET | `/metrics` | — | Prometheus text format |
| GET | `/metrics/json` | — | `{requests, latency, ...}` |

---

## 8. Error Handling Strategy

### Layer-Specific Handling

| Layer | Strategy | Example |
|---|---|---|
| **API** | Return structured HTTP errors; never expose internals | 401/403/422/429/500 with `{detail}` |
| **Middleware** | Catch-all; log; return 500 | Rate limit exceeded → 429 |
| **Agents** | Record error in `AgentRun.error`; return partial result | Bedrock timeout → return retrieved docs without generation |
| **Retrieval** | Degrade gracefully; return fewer results | OpenSearch down → pgvector-only results |
| **Generation** | Citation validation failure → fallback response | Hallucination → "I found relevant documents but cannot generate a reliable answer" |
| **Ingestion** | SQS visibility timeout + DLQ | Worker crash → message re-processed; 3 failures → DLQ |

### HTTP Status Codes

| Code | Meaning | When |
|---|---|---|
| 200 | Success | Normal response |
| 202 | Accepted | Ingestion queued |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Missing/expired token |
| 403 | Forbidden | Insufficient role |
| 404 | Not Found | Resource doesn't exist |
| 422 | Validation Error | Pydantic schema violation |
| 429 | Rate Limited | Sliding window exceeded |
| 500 | Server Error | Unexpected failure (logged) |

---

## 9. Configuration Management

### Environment-Based Configuration

All configuration is managed through `config/settings.py` using Pydantic `BaseSettings`:

```text
Environment Variable         Default              Description
────────────────────────────────────────────────────────────────────
APP_NAME                     indyleg              Application name
APP_ENV                      development          dev/staging/production
AWS_REGION                   us-east-1            AWS region
AWS_PROFILE                  (none)               AWS profile name
BEDROCK_MODEL_ID             anthropic.claude...  LLM model ID
BEDROCK_EMBED_MODEL_ID       amazon.titan-emb...  Embedding model ID
DATABASE_URL                 postgresql://...     PostgreSQL connection
OPENSEARCH_ENDPOINT          https://localhost    OpenSearch URL
SQS_QUEUE_URL                (none)               Ingestion queue URL
S3_BUCKET                    indyleg-documents    Document storage
JWT_SECRET_KEY               (generated)          Token signing key
RATE_LIMIT_RPM               60                   Requests per minute
REDIS_URL                    redis://localhost     Redis connection
SECRET_RESOLUTION_ORDER      ssm,secretsmanager   Secrets cascade
```

### Secret Resolution Order

```text
1. SSM Parameter Store       /indyleg/{env}/{key}
2. AWS Secrets Manager       indyleg/{env}/{key}
3. Environment variable      {KEY}
```

Secrets are cached with an LRU cache (maxsize=128) and TTL based on configuration.
