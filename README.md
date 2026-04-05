# IndyLeg — Indiana Legal RAG Platform

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6.svg)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock-FF9900.svg)](https://aws.amazon.com/bedrock/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/Anteneh-T-Tessema/legalairag/actions/workflows/ci.yml/badge.svg)](https://github.com/Anteneh-T-Tessema/legalairag/actions)

> **AI-powered legal research and document intelligence for Indiana courts.**
> A production-grade Retrieval-Augmented Generation (RAG) system built on AWS Bedrock — designed for attorneys, clerks, and legal staff who need fast, citation-grounded answers from Indiana case law, statutes, and court filings.

---

## Table of Contents

1. [Why IndyLeg?](#1-why-indyleg)
2. [What Is RAG?](#2-what-is-rag)
3. [System Architecture](#3-system-architecture)
4. [Subsystem Deep Dives](#4-subsystem-deep-dives)
   - [Ingestion Pipeline](#41-ingestion-pipeline)
   - [Query Processing](#42-query-processing)
   - [Hybrid Retrieval](#43-hybrid-retrieval)
   - [Re-ranking](#44-re-ranking)
   - [Answer Generation](#45-answer-generation)
   - [Agent Orchestration](#46-agent-orchestration)
5. [Authentication & Security](#5-authentication--security)
6. [Database Schema](#6-database-schema)
7. [API Reference](#7-api-reference)
8. [Configuration Reference](#8-configuration-reference)
9. [Project Structure](#9-project-structure)
10. [Local Development](#10-local-development)
11. [Running Tests](#11-running-tests)
12. [Ingestion CLI](#12-ingestion-cli)
13. [AWS Deployment](#13-aws-deployment)
14. [Performance](#14-performance)
15. [Design Decisions](#15-design-decisions)
16. [Troubleshooting](#16-troubleshooting)
17. [Contributing](#17-contributing)
18. [License](#18-license)

---

## 1. Why IndyLeg?

Legal research is time-consuming, error-prone, and expensive. An attorney searching for precedent on an eviction case in Marion County must manually:

- Search multiple court portals (Odyssey, Tyler, PACER)
- Read dozens of case documents
- Cross-reference Indiana Code statutes
- Verify citations before relying on them

IndyLeg automates this entire workflow. It continuously ingests documents from the Indiana courts system, indexes them with both semantic and keyword search, and allows staff to ask plain-English questions and receive **cite-grounded answers** — every claim backed by a document chunk with a verifiable source reference.

**Key properties:**

| Property | Detail |
|---|---|
| **Citation-grounded** | Every generated sentence is anchored to a retrieved source; hallucinations are detected and blocked |
| **Role-aware access** | Admin / Attorney / Clerk / Viewer roles with JWT |
| **Hybrid retrieval** | Dense (pgvector) + Sparse (BM25) fused via Reciprocal Rank Fusion |
| **Indiana-specific** | Understands `IC §` citation patterns, county jurisdictions, case type taxonomy |
| **Production-ready** | SQS dead-letter queues, ECS auto-scaling, CloudWatch audit logs, GitHub Actions CI |

---

## 2. What Is RAG?

**Retrieval-Augmented Generation (RAG)** is an architecture pattern that separates *what the AI knows* from *what it can look up*. Rather than relying solely on knowledge baked into a large language model's weights (which can be stale or hallucinated), a RAG system:

1. **Retrieves** relevant passages from an up-to-date document store
2. **Augments** the LLM's prompt with those passages as verified context
3. **Generates** an answer grounded in that context

```text
  WITHOUT RAG                          WITH RAG
  ───────────                          ────────
  User Question                        User Question
       │                                    │
       ▼                                    ▼
  LLM (frozen weights)            ┌── Retriever ──┐
       │                          │  (pgvector +  │
       ▼                          │   BM25 + RRF) │
  Answer ← may hallucinate        └───────┬───────┘
                                          │ retrieved passages
                                          ▼
                                    LLM (with context)
                                          │
                                          ▼
                                    Grounded Answer
                                    + [SOURCE: doc-id]
```

### Why RAG Fits Legal Research

Legal answers must be **verifiable**. A lawyer cannot cite "the AI said so" — they need the docket entry, statute section, or case holding. RAG produces traceable answers where every factual claim maps back to a document chunk that was actually retrieved. The IndyLeg citation validator enforces this: any claim in the response that cannot be matched to a retrieved chunk triggers a fallback response rather than a plausible-sounding hallucination.

---

## 3. System Architecture

### High-Level Overview

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         INDYLEG — INDIANA LEGAL RAG PLATFORM                    │
│                                                                                 │
│  ╔═══════════════╗    ╔════════════════════╗    ╔══════════════════════════╗    │
│  ║  React UI     ║    ║   FastAPI           ║    ║  Agent Layer             ║    │
│  ║  (Vite + TS)  ║◄──►║   /api/v1           ║◄──►║                          ║    │
│  ║               ║    ║                    ║    ║  ┌──────────────────────┐ ║    │
│  ║  • Ask tab    ║    ║  • /search         ║    ║  │ CaseResearchAgent    │ ║    │
│  ║  • Search tab ║    ║  • /search/ask     ║    ║  │ (5-step RAG pipeline)│ ║    │
│  ║  • Chat tab   ║    ║  • /auth/token     ║    ║  ├──────────────────────┤ ║    │
│  ║  • Documents  ║    ║  • /health         ║    ║  │ SummarizationAgent   │ ║    │
│  ╚═══════════════╝    ╚═════════╦══════════╝    ║  │ (parties, holdings,  │ ║    │
│         ▲                       ║               ║  │  citations, deadlines│ ║    │
│         │ JWT Bearer            ║               ║  └──────────────────────┘ ║    │
│         │                       ▼               ║  Audit-logged, run_id     ║    │
│  ╔══════╩══════════════════════════════════╗    ╚══════════════════════════╝    │
│  ║              RETRIEVAL LAYER            ║                                    │
│  ║                                         ║                                    │
│  ║  QueryParser ──▶ Embedder ──▶ HybridSearch ──▶ CrossEncoder                 │
│  ║  ┌──────────┐   ┌────────┐   ┌──────────────┐ ┌──────────────────────┐     │
│  ║  │jurisdiction│  │Bedrock │   │ pgvector     │ │ ms-marco-MiniLM-L-6  │     │
│  ║  │county     │  │Titan v2│   │ cosine sim   │ │ (query, chunk) pairs │     │
│  ║  │case type  │  │1024-dim│   ├──────────────┤ │ sorted by score      │     │
│  ║  │IC §       │  │vectors │   │ OpenSearch   │ └──────────────────────┘     │
│  ║  │ citations │  └────────┘   │ BM25 keyword │                              │
│  ║  └──────────┘                ├──────────────┤                              │
│  ║                              │ RRF fusion   │                              │
│  ║                              │  k = 60      │                              │
│  ║                              └──────────────┘                              │
│  ╚══════════════════════════════╦════════════════════════════════════════════╝ │
│                                 ║                                              │
│  ╔══════════════════════════════╩════════════════════════════════════════════╗ │
│  ║              GENERATION LAYER                                             ║ │
│  ║                                                                           ║ │
│  ║  SystemPrompt ──▶ Bedrock Claude 3.5 Sonnet ──▶ CitationValidator        ║ │
│  ║  (citation-        (temp=0.0, max_tokens=        ([SOURCE:id] exists?    ║ │
│  ║   enforced          4096, Converse API)            fallback if not)       ║ │
│  ║   instructions)                                                           ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                                                                │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║              INGESTION LAYER                                              ║ │
│  ║                                                                           ║ │
│  ║  IndianaCourts ──▶ SQS Queue ──▶ Worker Pool ──▶ Embedder ──▶ pgvector  ║ │
│  ║  API (Odyssey)     (+ DLQ,        (async,          Bedrock                ║ │
│  ║  + CLI             3 retries)      concurrency=4)   Titan v2)             ║ │
│  ║                    ║                                       ║               ║ │
│  ║                    ║                              BM25 ──▶ OpenSearch      ║ │
│  ║                    ▼                                       ║               ║ │
│  ║                   S3 (raw)                        S3 ──▶ (processed)      ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
│                                                                                │
│  ╔═══════════════════════════════════════════════════════════════════════════╗ │
│  ║  INFRASTRUCTURE (AWS CDK)                                                 ║ │
│  ║  S3 │ SQS+DLQ │ Aurora PostgreSQL + pgvector │ OpenSearch │ ECS Fargate  ║ │
│  ║  Bedrock (Claude 3.5 Sonnet + Titan Embed v2) │ CloudWatch │ ALB         ║ │
│  ╚═══════════════════════════════════════════════════════════════════════════╝ │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Ingestion Data Flow

```text
  Indiana Courts Portal
  (Odyssey / Tyler API)
          │
          │  CourtCase + CaseDocument
          ▼
  ┌─────────────────┐
  │  IndianaCourts  │  rate-limited, exponential backoff
  │  API Client     │  max 5 concurrent requests
  └────────┬────────┘
           │  IngestionMessage (source_id, doc_url, metadata)
           ▼
  ┌─────────────────┐
  │   SQS Queue     │  batch send (up to 10)
  │   (FIFO + DLQ)  │  visibility timeout: 5 min
  └────────┬────────┘  max retries before DLQ: 3
           │  long-poll (20s wait)
           ▼
  ┌─────────────────────────────────────────────────────┐
  │  Worker Pool (asyncio, concurrency=4)               │
  │                                                     │
  │  ┌──────────┐   ┌──────────┐   ┌────────────────┐  │
  │  │  Download │──▶│  Parse   │──▶│  LegalChunker  │  │
  │  │ S3 / HTTP │   │ PDF/DOCX │   │                │  │
  │  └──────────┘   │ HTML/TXT │   │  • detect §    │  │
  │                 └──────────┘   │  • sliding win │  │
  │                                │  • IC § extract│  │
  │                                └───────┬────────┘  │
  │                                        │  List[Chunk]
  │                                        ▼
  │                               ┌────────────────┐   │
  │                               │BedrockEmbedder │   │
  │                               │                │   │
  │                               │ batch=128      │   │
  │                               │ Titan Embed v2 │   │
  │                               │ 1024-dim vecs  │   │
  │                               └───────┬────────┘   │
  └───────────────────────────────────────┼────────────┘
                                          │
                          ┌───────────────┼────────────────┐
                          ▼               ▼                ▼
                    pgvector         OpenSearch           S3
                 (cosine vectors)  (BM25 index)     (processed chunks
                  legal_chunks       indyleg-           as JSON)
                    table            legal-docs
```

### Query / Answer Data Flow

```text
  User: "What is Indiana's eviction notice requirement?"
          │
          ▼
  ┌────────────────────────────────────────────────────┐
  │  QueryParser                                       │
  │  • jurisdiction → "Marion County"                  │
  │  • case_type    → CaseType.CIVIL                   │
  │  • citations    → ["IC 32-31-1-6"]                 │
  │  • bm25_keywords → ["eviction", "notice", "tenant"]│
  └──────────┬─────────────────────────────────────────┘
             │
             ▼
  ┌────────────────────┐
  │  BedrockEmbedder   │  → 1024-dim query vector
  │  Titan Embed v2    │
  └──────────┬─────────┘
             │
             ▼
  ┌─────────────────────────────────────────────────────┐
  │  HybridSearch                                       │
  │                                                     │
  │  ┌─────────────────┐    ┌──────────────────────┐   │
  │  │  pgvector       │    │  OpenSearch (BM25)   │   │
  │  │  cosine sim     │    │  keyword match       │   │
  │  │  top 80 results │    │  top 80 results      │   │
  │  └────────┬────────┘    └──────────┬───────────┘   │
  │           │                        │               │
  │           └──────────┬─────────────┘               │
  │                      ▼                             │
  │           ┌──────────────────┐                     │
  │           │  RRF Fusion      │  score = Σ 1/(k+r)  │
  │           │  k = 60          │  k = 60              │
  │           │  top 20 merged   │                     │
  │           └──────────────────┘                     │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  CrossEncoder (ms-marco-MiniLM-L-6-v2)              │
  │  Scores each (query, chunk) pair independently      │
  │  Returns top 5 by cross-attention score             │
  └──────────────────────┬──────────────────────────────┘
                         │  5 high-precision chunks
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  Bedrock Claude 3.5 Sonnet                          │
  │  System prompt: cite every claim with [SOURCE: id]  │
  │  User prompt: question + 5 numbered context chunks  │
  │  Temperature: 0.0 (deterministic, no creativity)    │
  │  Max tokens: 4096                                   │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
  ┌─────────────────────────────────────────────────────┐
  │  CitationValidator                                  │
  │  • Extract all [SOURCE: x] from response            │
  │  • Verify each x exists in retrieved chunks         │
  │  • Flag sentences with no source anchor             │
  │  • Fail-safe: return structured fallback if invalid │
  └──────────────────────┬──────────────────────────────┘
                         │
                         ▼
              Grounded Answer + source metadata
              confidence score + run_id for audit
```

---

## 4. Subsystem Deep Dives

### 4.1 Ingestion Pipeline

The ingestion pipeline turns raw court documents into searchable knowledge. It is designed to handle the irregular, citation-heavy structure of legal text.

#### Legal-Aware Document Chunking

Generic text splitters break documents at arbitrary character boundaries, severing citations and section headings from their context. The `LegalChunker` solves this by:

**Section boundary detection** — The chunker scans for structural headings using patterns like:
- `SECTION \d+`, `ARTICLE [IVX]+`, `§ \d+`
- Roman numeral headings (`I.`, `II.`, `III.`)
- Capitalised headings typical in court orders

When a boundary is detected, the current chunk is closed and a new one begins, preserving each section as a semantic unit.

**Indiana Code citation extraction** — Every chunk is scanned for `IC \d+-\d+-\d+-\d+` patterns (e.g., `IC 32-31-1-6`). Extracted citations are stored in the chunk's metadata, enabling citation-based filtering at query time.

**Sliding window with sentence awareness** — For long sections, the chunker applies a sliding window:
- Window size: **512 characters**
- Overlap: **64 characters**
- Split points prefer sentence boundaries (`.`, `?`, `!`) rather than arbitrary positions, keeping individual sentences intact

**Metadata enrichment** — Each chunk carries:

```json
{
  "chunk_id": "doc-abc123-chunk-007",
  "source_id": "case-49D01-2023-MF-001234",
  "source_type": "court_filing",
  "document_url": "s3://indyleg-raw-documents/...",
  "section_heading": "FINDINGS OF FACT",
  "page_number": 3,
  "citations": ["IC 32-31-1-6", "IC 32-31-3-9"],
  "jurisdiction": "Marion County",
  "case_type": "civil",
  "char_start": 1024,
  "char_end": 1536
}
```

#### Bedrock Embedder

The `BedrockEmbedder` converts text chunks into 1024-dimensional dense vectors using **Amazon Titan Embed Text v2** (`amazon.titan-embed-text-v2:0`). Key design choices:

- **Batch processing** — Chunks are embedded in batches of 128, reducing API round-trips by ~128×
- **Concurrency limiting** — An `asyncio.Semaphore` caps in-flight Bedrock calls to prevent rate limit errors
- **Thread executor wrapping** — The boto3 `invoke_model` call is a synchronous blocking I/O call; it is wrapped in `asyncio.get_event_loop().run_in_executor()` so the async worker can process multiple batches concurrently
- **Separate query embedding** — A dedicated `embed_query()` method handles single-query embedding at query time, reusing the same model configuration

#### SQS-Driven Worker

The worker pool decouples document discovery from embedding compute. This means:

- The Indiana Courts API client can discover and enqueue thousands of documents immediately
- Workers pull from the queue at their own pace, limited by `INGESTION_WORKER_CONCURRENCY=4`
- If a document fails processing (corrupt PDF, network timeout, Bedrock throttle), it is retried up to **3 times** before routing to the **Dead-Letter Queue (DLQ)** for manual inspection
- The visibility timeout is **5 minutes** for the ingestion queue and **10 minutes** for the embedding queue, accommodating slow document downloads and large batch embedding calls

#### Indiana Courts Source Client

The `IndianaCourtsCasesClient` wraps the Indiana Odyssey/Tyler court portal API:

```text
Methods:
  search_cases(query, county, case_type, date_from, date_to)
  get_case(case_number)
  download_document(document_id) → bytes
  list_recent_filings(county, days_back)

Safety features:
  • Rate limiting with exponential backoff
  • asyncio.Semaphore(5) — max 5 concurrent calls
  • Case number sanitization to strip injection characters
  • CaseDocument dataclass with typed fields
```

---

### 4.2 Query Processing

Before any search occurs, the `QueryParser` decomposes the user's raw question into structured components:

```text
Input:  "What are the notice requirements for evicting a tenant in Marion County?"

Output:
  normalized_query: "notice requirements evicting tenant Marion County"
  jurisdiction:     "Marion County"
  case_type:        CaseType.CIVIL
  citations:        []           ← none found in this query
  bm25_keywords:    ["notice", "requirements", "evicting", "tenant"]
                    (stopwords like "what", "are", "the", "a", "in" removed)
```

This structured output enables **metadata pre-filtering** in pgvector (`WHERE metadata->>'jurisdiction' = 'Marion County'`) before the vector similarity search, dramatically reducing the candidate set and improving precision.

---

### 4.3 Hybrid Retrieval

No single retrieval method is best for all queries. IndyLeg fuses two complementary approaches:

#### Dense Retrieval (pgvector)

Dense retrieval uses the same Titan Embed v2 model to embed the query and then performs a **cosine similarity search** over the 1024-dimensional vector space. It excels at:
- Semantic similarity ("tenant removal procedure" matches "eviction process")
- Paraphrase matching
- Implicit concept queries with no exact keyword overlap

#### Sparse Retrieval (BM25 / OpenSearch)

BM25 is a classical probabilistic keyword ranking algorithm. Given a query term, it scores documents by term frequency (how often the word appears) divided by document length. It excels at:
- Exact statutory citation matching (`IC 32-31-1-6`)
- Proper noun matching (case names, judge names)
- Rare or technical terms the embedding model may handle poorly

#### Reciprocal Rank Fusion (RRF)

RRF is the fusion algorithm that merges the two ranked lists. For each document appearing in either list, its score is:

$$\text{score}(d) = \sum_{i \in \{vector, bm25\}} \frac{1}{k + r_i(d)}$$

where $r_i(d)$ is the rank of document $d$ in list $i$, and $k = 60$ is a smoothing constant that prevents very high ranks from dominating.

**Why RRF over score normalization?** RRF is rank-based, so it does not require the two retrieval systems to produce comparable relevance scores (cosine similarity from pgvector is in [-1,1]; BM25 scores are unbounded positive numbers). RRF correctly handles cases where a document ranks #1 in BM25 but is absent from the vector results — it still gets credit.

Both the vector and BM25 search over-fetch by 4× (`top_k × 4`) to give the re-ranker a richer candidate pool after fusion.

---

### 4.4 Re-ranking

The cross-encoder re-ranker (`sentence-transformers/ms-marco-MiniLM-L-6-v2`) provides a precision boost beyond what bi-encoder retrieval can achieve.

**Bi-encoder vs. Cross-encoder:**

```text
Bi-encoder (retrieval):          Cross-encoder (re-ranking):
  Embed query once                  Score (query, doc) together
  Embed docs once (offline)         Model sees BOTH at once
  Dot product similarity            Full cross-attention
  Fast — O(1) per query             Slow — O(n) per query
  Good recall                       Better precision
```

The system uses bi-encoders (Titan Embed) at retrieval time to efficiently filter millions of chunks down to ~20, then applies the cross-encoder to re-score those 20 with full attention, returning the final top 5. This two-stage pipeline gets the best of both: the speed of embedding-based retrieval and the precision of cross-attention scoring.

The cross-encoder runs in a **thread executor** (same pattern as the embedder) to avoid blocking the async event loop during the CPU-bound model inference.

---

### 4.5 Answer Generation

#### Bedrock Converse API

The `BedrockClient` wraps the [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) with two methods:

| Method | Use case | Behaviour |
|---|---|---|
| `complete(prompt, system)` | Research agent, summarization | Returns full response string |
| `complete_stream(prompt, system)` | Future streaming UI | Async generator of text chunks |

Configuration:
- **Model**: `anthropic.claude-3-5-sonnet-20241022-v2:0`
- **Temperature**: `0.0` — fully deterministic; no creative variation
- **Max tokens**: `4096` — sufficient for multi-paragraph legal answers with full citations
- **System prompt**: Injects citation enforcement instructions before the user turn

#### Citation Validator (Hallucination Guard)

After generation, every response passes through the `CitationValidator`:

```text
Response text:
  "Indiana law requires 10 days notice before eviction [SOURCE: chunk-003].
   The landlord must also file in small claims court [SOURCE: chunk-007]."

Validation steps:
  1. Extract all [SOURCE: x] markers → ["chunk-003", "chunk-007"]
  2. Check each against retrieved_chunk_ids → both found ✓
  3. Scan sentences without any [SOURCE: ...] marker → none found ✓
  4. Result: ValidationResult(passed=True, warnings=[])

Failure case:
  "The penalty is $5,000 per violation."  ← no citation
  Result: ValidationResult(passed=False, warnings=["Uncited assertion detected"])
  Action: Return structured fallback response instead of potentially false claim
```

---

### 4.6 Agent Orchestration

#### CaseResearchAgent (5-Step Pipeline)

The research agent coordinates the full RAG pipeline:

```text
Step 1 — Parse Query
  Input:  raw user question (string)
  Output: ParsedQuery(jurisdiction, case_type, citations, bm25_keywords)
  Audit:  LOG step=parse, query_len, extracted_fields

Step 2 — Embed Query
  Input:  normalized query string
  Output: 1024-dim float vector
  Audit:  LOG step=embed, model=titan-embed-v2

Step 3 — Hybrid Search
  Input:  vector, bm25_keywords, metadata filters
  Output: ~20 candidates (RRF-fused from pgvector + BM25)
  Audit:  LOG step=search, vector_hits, bm25_hits, fused_count

Step 4 — Re-rank
  Input:  query + ~20 candidates
  Output: top 5 chunks (cross-encoder scored)
  Audit:  LOG step=rerank, top_score, score_distribution

Step 5 — Generate + Validate
  Input:  query, top 5 chunks, system prompt
  Output: validated response with confidence score
  Audit:  LOG step=generate, run_id, validation_passed, token_count
```

Each run is assigned a **`run_id`** (UUID) that threads through all five audit log entries. This enables full end-to-end tracing: when a user reports a bad answer, the `run_id` in the response lets an admin replay the exact query, see which chunks were retrieved, and determine whether the problem was retrieval or generation.

**Confidence estimation** — Computed from the cross-encoder scores of the top-5 chunks:
- If the top chunk scores > 0.8: `HIGH` confidence
- Scores 0.5–0.8: `MEDIUM`
- Below 0.5: `LOW` (response includes a caveat)

#### SummarizationAgent

Summarizes individual case documents using a structured extraction prompt:

```json
{
  "parties": ["Plaintiff: Smith, John", "Defendant: Johnson, Mary"],
  "key_holdings": ["Court found for defendant on eviction claim"],
  "citations": ["IC 32-31-1-6", "IC 32-31-3-9"],
  "deadlines": ["Response due: 2024-03-15"],
  "summary": "..."
}
```

---

## 5. Authentication & Security

### JWT Token Architecture

```text
POST /api/v1/auth/token  (login with username + password)
        │
        ▼
┌────────────────────────────────────────┐
│  Verify HMAC-SHA256(password + salt)   │
│  (password stored as hex(sha256(salt   │
│   + password)), random 32-byte salt)   │
└──────────────┬─────────────────────────┘
               │  credentials valid
               ▼
┌──────────────────────────────────────┐
│  create_access_token()               │  exp: +60 minutes, HS256
│  create_refresh_token()              │  exp: +7 days, HS256
└──────────────┬───────────────────────┘
               │
               ▼
  { "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer" }


POST /api/v1/auth/refresh
  Body: { "refresh_token": "eyJ..." }
  → validates refresh token, issues new access_token


GET /api/v1/... (protected endpoints)
  Header: Authorization: Bearer <access_token>
  → get_current_user() FastAPI Depends() decodes and validates JWT
  → require_role(Role.ATTORNEY) decorator checks roles claim
```

### Role Model

| Role | Access |
|---|---|
| `ADMIN` | All endpoints + ingestion management |
| `ATTORNEY` | Search, RAG answers, document viewer |
| `CLERK` | Search, document upload |
| `VIEWER` | Read-only search |

### Password Security

Passwords are hashed using:

```python
salt = secrets.token_bytes(32)               # cryptographically random
digest = hmac.new(salt, password.encode(), hashlib.sha256).hexdigest()
stored = f"{salt.hex()}:{digest}"
```

No plaintext passwords are stored or logged. The `AuditLogMiddleware` automatically redacts `Authorization` headers from request logs.

### API Security Headers

The FastAPI CORS middleware is configured with an explicit `allow_origins` list (not `*`). Swagger UI (`/docs`) is disabled in production (`app_env=production`) to prevent API enumeration.

---

## 6. Database Schema

### `legal_chunks` Table (PostgreSQL + pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE legal_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        TEXT UNIQUE NOT NULL,
    source_id       TEXT NOT NULL,
    source_type     TEXT NOT NULL,          -- 'court_filing', 'statute', 'ruling'
    document_url    TEXT,
    text            TEXT NOT NULL,
    embedding       VECTOR(1024),           -- pgvector 1024-dimensional column
    metadata        JSONB NOT NULL,         -- jurisdiction, case_type, citations, etc.
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for approximate nearest neighbor search
-- ef_construction=128 and m=16 are standard starting points
CREATE INDEX ON legal_chunks USING hnsw (embedding vector_cosine_ops)
WITH (ef_construction = 128, m = 16);

-- B-tree index for metadata filtering (jurisdiction, case_type)
CREATE INDEX ON legal_chunks USING gin (metadata);
```

**Why HNSW over IVFFlat?** HNSW (Hierarchical Navigable Small World) provides better recall at high query-per-second loads without requiring a training step. IVFFlat requires pre-computing cluster centroids (`VACUUM ANALYZE`) whenever the dataset changes significantly. For a legal corpus that grows continuously, HNSW is operationally simpler.

### OpenSearch Index (`indyleg-legal-docs`)

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "legal_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "stop"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "chunk_id":    { "type": "keyword" },
      "text":        { "type": "text", "analyzer": "legal_analyzer" },
      "source_id":   { "type": "keyword" },
      "jurisdiction":{ "type": "keyword" },
      "case_type":   { "type": "keyword" },
      "citations":   { "type": "keyword" }
    }
  }
}
```

---

## 7. API Reference

Base URL: `https://your-alb-dns/api/v1`
All endpoints except `/auth/token` and `/health` require `Authorization: Bearer <token>`.

---

### Authentication

#### `POST /auth/token` — Login

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

---

#### `POST /auth/refresh` — Refresh Access Token

**Request:**
```json
{ "refresh_token": "eyJ..." }
```

**Response `200 OK`:**
```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600 }
```

---

#### `GET /auth/me` — Current User Profile

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

### Search & RAG

#### `POST /search` — Hybrid Retrieval

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

---

#### `POST /search/ask` — RAG Answer Generation

Runs the full 5-step CaseResearchAgent pipeline: retrieval → re-ranking → generation → validation.

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
  "answer": "Under Indiana law, a landlord must provide at least 10 days written notice before initiating eviction proceedings [SOURCE: chunk-003]. For non-payment of rent, this notice must specifically state the amount owed and the cure period [SOURCE: chunk-007].",
  "sources": [
    {
      "chunk_id": "chunk-003",
      "text": "IC 32-31-1-6 provides that...",
      "source_id": "case-49D01-2023-MF-001234",
      "score": 0.923
    },
    {
      "chunk_id": "chunk-007",
      "text": "The notice must include...",
      "source_id": "statute-ic-32-31-1",
      "score": 0.887
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

### Health

#### `GET /health`

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

## 8. Configuration Reference

All configuration is via environment variables, loaded by Pydantic `BaseSettings` from `.env` or the environment. Secrets (API keys, DB passwords) must never be committed to version control.

| Variable | Default | Required | Description |
|---|---|---|---|
| `APP_ENV` | `development` | No | `development` \| `staging` \| `production` |
| `API_SECRET_KEY` | — | **Yes** | JWT signing key (≥ 32 random bytes) |
| `AWS_REGION` | `us-east-1` | No | AWS region for all services |
| `AWS_ACCESS_KEY_ID` | — | **Yes** | AWS credentials (use IAM role in ECS) |
| `AWS_SECRET_ACCESS_KEY` | — | **Yes** | AWS credentials |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | No | Titan Embed model ID |
| `BEDROCK_LLM_MODEL` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | No | Claude model ID |
| `BEDROCK_MAX_TOKENS` | `4096` | No | Max tokens for generation |
| `S3_BUCKET_RAW` | `indyleg-raw-documents` | No | S3 bucket for raw court documents |
| `S3_BUCKET_PROCESSED` | `indyleg-processed-chunks` | No | S3 bucket for processed chunks |
| `SQS_INGESTION_QUEUE_URL` | — | **Yes** | SQS URL for document ingestion |
| `SQS_EMBEDDING_QUEUE_URL` | — | **Yes** | SQS URL for embedding jobs |
| `DATABASE_URL` | — | **Yes** | PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `VECTOR_DIMENSION` | `1024` | No | Embedding vector dimension |
| `OPENSEARCH_HOST` | `localhost` | No | OpenSearch cluster endpoint |
| `OPENSEARCH_PORT` | `9200` | No | OpenSearch port |
| `INDIANA_COURTS_API_BASE` | — | **Yes** | Indiana Odyssey/Tyler API base URL |
| `INDIANA_COURTS_API_KEY` | — | **Yes** | API key for courts portal |
| `EMBEDDING_BATCH_SIZE` | `128` | No | Chunks per Bedrock embedding call |
| `INGESTION_WORKER_CONCURRENCY` | `4` | No | Parallel SQS worker coroutines |
| `RERANK_TOP_K` | `20` | No | Candidates fed to cross-encoder |
| `RETRIEVAL_TOP_K` | `5` | No | Final chunks returned to LLM |
| `LOG_LEVEL` | `INFO` | No | Structured log level |

Generate a secure `API_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 9. Project Structure

```text
indyleg/
├── .env.example                    # Template — copy to .env and fill in secrets
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions: backend tests, tsc+build, docker smoke
├── config/
│   ├── settings.py                 # Pydantic BaseSettings — single config source of truth
│   └── logging_config.py          # structlog JSON logging setup
├── ingestion/
│   ├── cli.py                      # Click CLI: recent / search / case subcommands
│   ├── sources/
│   │   ├── indiana_courts.py       # Async Indiana Odyssey/Tyler portal client
│   │   └── document_parser.py     # PDF/DOCX/HTML/TXT → plain text
│   ├── pipeline/
│   │   ├── chunker.py              # Legal-aware sliding window chunker
│   │   ├── embedder.py             # Bedrock Titan Embed v2, batch + semaphore
│   │   └── worker.py              # SQS-driven async orchestrator
│   └── queue/
│       └── sqs.py                  # SQS producer/consumer, long-poll, batch
├── retrieval/
│   ├── hybrid_search.py            # pgvector + BM25 + RRF fusion
│   ├── reranker.py                 # Cross-encoder ms-marco-MiniLM-L-6-v2
│   └── query_parser.py            # Jurisdiction / case_type / citation extraction
├── generation/
│   ├── bedrock_client.py           # Bedrock Converse API wrapper
│   └── validator.py               # Citation validator + hallucination guard
├── agents/
│   ├── research_agent.py           # 5-step CaseResearchAgent + audit trail
│   └── summarization_agent.py     # Structured document summarization
├── api/
│   ├── auth.py                     # JWT creation, HMAC-SHA256 password hashing
│   ├── main.py                     # FastAPI app, CORS, AuditLogMiddleware
│   ├── schemas.py                  # Pydantic request/response models
│   └── routers/
│       ├── search.py               # POST /search  POST /search/ask
│       └── auth_router.py         # POST /auth/token  POST /auth/refresh  GET /auth/me
├── ui/                             # React + TypeScript + Vite frontend
│   ├── src/
│   │   ├── App.tsx                 # Tab navigation, auth gate, logout
│   │   ├── index.css              # Full responsive stylesheet (CSS variables)
│   │   └── components/
│   │       ├── ChatInterface.tsx
│   │       ├── SearchResults.tsx
│   │       ├── DocumentUpload.tsx
│   │       └── LoginForm.tsx
│   ├── tsconfig.json              # strict, jsx:react-jsx, moduleResolution:bundler
│   └── vite.config.ts             # proxy /api → localhost:8000, port 3000
├── infrastructure/
│   ├── cdk/
│   │   ├── app.py                  # CDK app entry point
│   │   └── stacks/
│   │       ├── ingestion_stack.py  # S3 + SQS + worker Lambda/ECS
│   │       └── api_stack.py       # ECS Fargate + ALB, Aurora pgvector, OpenSearch
│   ├── docker/
│   │   ├── Dockerfile             # Multi-stage production image
│   │   └── init.sql               # PostgreSQL schema + pgvector extensions
│   └── deploy.sh                  # cdk bootstrap + cdk deploy --all
├── tests/
│   ├── unit/
│   │   ├── test_chunker.py
│   │   ├── test_embedder.py
│   │   ├── test_hybrid_search.py
│   │   ├── test_reranker.py
│   │   ├── test_query_parser.py
│   │   ├── test_validator.py
│   │   ├── test_research_agent.py
│   │   ├── test_summarization_agent.py
│   │   └── test_auth.py
│   └── integration/
│       ├── test_sqs.py             # End-to-end SQS produce/consume
│       └── test_bedrock.py        # Live Bedrock embedding + generation
├── docker-compose.yml              # Local dev: postgres, opensearch, localstack
└── requirements.txt               # Python dependencies
```

---

## 10. Local Development

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Backend |
| Node.js | 18+ | Frontend build |
| Docker + Docker Compose | Latest | Local services |
| AWS CLI | v2 | Bedrock / S3 access |
| AWS credentials | — | `~/.aws/credentials` or env vars |

### Step-by-Step Setup

**1. Clone the repository**

```bash
git clone https://github.com/Anteneh-T-Tessema/legalairag.git
cd legalairag
```

**2. Create and activate the Python virtual environment**

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

**3. Install Python dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**4. Configure environment variables**

```bash
cp .env.example .env
# Edit .env — fill in AWS credentials, DB URL, SQS URLs, Indiana Courts API key
# Generate a secret key:
python -c "import secrets; print(secrets.token_hex(32))"
```

**5. Start local services with Docker Compose**

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 15** with `pgvector` extension on port `5432`
- **OpenSearch 2.x** on port `9200`
- **LocalStack** (S3 + SQS emulation) on port `4566`
- The init script at `infrastructure/docker/init.sql` runs automatically, creating the `legal_chunks` table and HNSW index

Wait for services to be healthy:

```bash
docker compose ps   # all should show "healthy"
```

**6. Run the FastAPI backend**

```bash
uvicorn api.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the interactive API documentation (Swagger UI, available in development mode only).

**7. Start the React frontend**

```bash
cd ui
npm install
npm run dev
```

The UI is available at `http://localhost:3000`. API calls to `/api/...` are proxied to the FastAPI backend at `localhost:8000`.

**8. Seed test data (optional)**

```bash
# Ingest recent Marion County filings (dry-run — no queue write)
python -m ingestion.cli recent --county "Marion County" --days 7 --dry-run

# Live ingest (requires SQS + LocalStack running)
python -m ingestion.cli recent --county "Marion County" --days 7
```

**9. Log in with seed credentials**

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | ADMIN |
| `attorney` | `attorney123` | ATTORNEY |
| `clerk` | `clerk123` | CLERK |

> **Security note:** Change all seed passwords immediately before any shared or production deployment.

---

## 11. Running Tests

### Unit Tests

```bash
pytest tests/unit/ -v
```

All 19 unit tests cover: chunker (section detection, overlap), embedder (batching, semaphore), hybrid search (RRF formula), reranker (score ordering), query parser (citation extraction, jurisdiction), citation validator (hallucination detection), research agent (pipeline steps), summarization agent (structured output), and auth (JWT creation, role verification).

### Integration Tests

Integration tests require live AWS credentials and running local services (Docker Compose).

```bash
# Requires LocalStack for SQS
pytest tests/integration/test_sqs.py -v

# Requires real AWS Bedrock access
pytest tests/integration/test_bedrock.py -v
```

### Full Test Suite with Coverage

```bash
pytest --cov=. --cov-report=html --cov-report=term-missing
open htmlcov/index.html
```

### Linting and Type Checking

```bash
ruff check .                # fast Python linter
mypy . --ignore-missing-imports   # static type checking
```

Frontend type checking:

```bash
cd ui && npx tsc --noEmit
```

---

## 12. Ingestion CLI

The ingestion CLI (`ingestion/cli.py`) provides three subcommands for populating the document index from the Indiana courts portal.

### `recent` — Ingest Recent Filings

Fetches all new filings from the specified county for the last N days.

```bash
python -m ingestion.cli recent \
  --county "Marion County" \
  --days 7 \
  [--dry-run]
```

| Option | Default | Description |
|---|---|---|
| `--county` | `"Marion County"` | Indiana county name |
| `--days` | `7` | How many days back to search |
| `--dry-run` | `False` | Print filings without queuing to SQS |

### `search` — Search and Ingest by Query

Searches the courts portal for cases matching a keyword and ingests results.

```bash
python -m ingestion.cli search \
  --query "residential eviction" \
  --county "Hamilton County" \
  --case-type CIVIL \
  [--dry-run]
```

### `case` — Ingest a Specific Case

Ingests all documents for a single case by case number.

```bash
python -m ingestion.cli case \
  --case-number "49D01-2023-MF-001234" \
  [--dry-run]
```

### Dry-Run Mode

All three subcommands support `--dry-run`. In this mode, the CLI prints the would-be ingestion messages to stdout without writing to SQS or triggering any embedding. Useful for:

- Verifying case discovery before committing to a large ingest
- CI/CD pipeline smoke tests
- Debugging case number sanitization

---

## 13. AWS Deployment

### Infrastructure Overview

The CDK stacks deploy the following AWS resources:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  VPC (private subnets for all compute and data)                         │
│                                                                         │
│  ┌──────────────┐    ┌───────────────────────────────────────────────┐  │
│  │     ALB      │───▶│  ECS Fargate Cluster                          │  │
│  │  (public)    │    │                                               │  │
│  └──────────────┘    │  ┌─────────────────┐  ┌──────────────────┐  │  │
│                      │  │  API Service     │  │  Worker Service  │  │  │
│                      │  │  desired: 2      │  │  desired: 1      │  │  │
│                      │  │  max: 6          │  │  max: 4          │  │  │
│                      │  │  CPU scale: 70%  │  │  SQS scale       │  │  │
│                      │  └─────────────────┘  └──────────────────┘  │  │
│                      └───────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─────────────────────┐  ┌───────────────┐  ┌────────────────────┐   │
│  │  Aurora PostgreSQL  │  │  OpenSearch   │  │  S3 Buckets        │   │
│  │  + pgvector ext     │  │  Domain       │  │  raw + processed   │   │
│  │  Multi-AZ           │  │  2 data nodes │  │  versioned         │   │
│  └─────────────────────┘  └───────────────┘  └────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  SQS: ingestion-queue + ingestion-dlq + embedding-queue          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Deployment Steps

**Prerequisites:**
```bash
npm install -g aws-cdk
pip install aws-cdk-lib constructs
aws configure   # ensure credentials have CDK/CloudFormation permissions
```

**1. Bootstrap CDK** (first time only, per account/region):

```bash
cd infrastructure
cdk bootstrap aws://ACCOUNT_ID/us-east-1
```

**2. Deploy all stacks:**

```bash
./deploy.sh production
# or: ENV=production cdk deploy --all --outputs-file outputs-production.json
```

The script deploys stacks in dependency order:
1. `IndylegNetworkStack` — VPC, subnets, security groups
2. `IndylegDataStack` — Aurora, OpenSearch, S3, SQS
3. `IndylegApiStack` — ECS Fargate (API + worker), ALB, IAM roles

**3. Set secrets in AWS Secrets Manager:**

```bash
aws secretsmanager create-secret \
  --name indyleg/production/api-secret-key \
  --secret-string "$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

**4. Run database migrations:**

After first deploy, connect to Aurora and run `infrastructure/docker/init.sql` to create the `legal_chunks` table and pgvector index.

**5. Seed initial data:**

```bash
# Using the deployed SQS queue URL from outputs-production.json
SQS_INGESTION_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456/indyleg-prod-ingestion \
python -m ingestion.cli recent --county "Marion County" --days 30
```

### IAM Permissions

The ECS task role requires:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject"], "Resource": "arn:aws:s3:::indyleg-*/*" },
    { "Effect": "Allow", "Action": ["sqs:SendMessage","sqs:ReceiveMessage","sqs:DeleteMessage"], "Resource": "arn:aws:sqs:*:*:indyleg-*" }
  ]
}
```

The CDK stack creates this role automatically via `api_stack.py`.

---

## 14. Performance

### Latency Targets (p95)

| Operation | Target | Notes |
|---|---|---|
| Full RAG answer (`/search/ask`) | < 3s | Embedding + retrieval + generation |
| Hybrid search only (`/search`) | < 500ms | pgvector + BM25 + RRF |
| Query embedding | < 200ms | Titan Embed v2 via Bedrock |
| Cross-encoder re-ranking | < 150ms | MiniLM-L6 CPU inference |
| Document ingestion (per chunk) | ~20ms | Excludes download time |

### Throughput

| Component | Capacity |
|---|---|
| API (2 ECS tasks baseline) | ~50 concurrent queries |
| ECS auto-scaling | 2 → 6 tasks at 70% CPU |
| Ingestion worker | 4 concurrent workers × 128 chunks/batch |
| Bedrock quotas | Managed by AWS service quotas (request increase via console) |

### Cost Optimisation

- Titan Embed v2 is called only during ingestion (offline) and once per query (very low marginal cost)
- Claude 3.5 Sonnet is invoked at `temperature=0.0` with `max_tokens=4096`; most legal answers are < 1000 tokens
- pgvector HNSW index uses `ef_search=64` at query time (configurable) to trade recall for speed
- OpenSearch `t3.medium.search` data nodes are sufficient for < 10M chunks; scale to `m6g.large` for production loads

---

## 15. Design Decisions

### Why Hybrid Search (not just vector search)?

Legal text contains precise statutory references (`IC 32-31-1-6`) and proper nouns (judge names, party names, case numbers) that dense embeddings handle poorly. A query for "IC 32-31-1-6" should retrieve documents containing exactly that citation — BM25 excels at this. Conversely, a semantic query ("landlord's duty to maintain a habitable unit") benefits from embedding-based matching that finds paraphrases BM25 would miss. RRF combines both without requiring score normalization.

### Why `temperature=0.0` for the LLM?

Legal answers must be **reproducible and deterministic**. If an attorney asks the same question twice, they should get the same answer. Temperature > 0 introduces stochastic variation; in a legal context, this creates unpredictability in advice. `temperature=0.0` maximises the most probable token at each step, giving consistent, auditable responses.

### Why Cross-Encoder Re-ranking After Retrieval?

Bi-encoders (Titan Embed) encode query and documents independently, making retrieval fast at the cost of precision. Cross-encoders process query and document together with cross-attention, seeing their interaction — which leads to much better relevance judgments. The two-stage pipeline (bi-encoder → cross-encoder) gets the best of both: O(1) embedding-based retrieval for recall, O(n) cross-encoder scoring for precision on the candidate set.

### Why pgvector Over Pinecone / Weaviate?

- Co-location with the application data in Aurora PostgreSQL reduces network hops
- RDS/Aurora pgvector is natively available in AWS, simplifying IAM and VPC network policies
- JSONB metadata is stored in the same table, enabling combined SQL + vector queries in a single database round-trip
- No additional managed service to secure, monitor, and pay for

### Why SQS for Ingestion (not direct function calls)?

The Indiana courts portal can return thousands of new filings at once. A synchronous ingestion call would time out. SQS provides natural backpressure: the producer fills the queue quickly, and the worker pool drains it at a controlled rate. The DLQ ensures no document is silently dropped on transient failures.

---

## 16. Troubleshooting

### `vector extension not found`

```bash
# Connect to PostgreSQL and run:
CREATE EXTENSION IF NOT EXISTS vector;
# Then re-run init.sql
```

### Bedrock `AccessDeniedException`

Ensure your IAM user/role has `bedrock:InvokeModel` permission and that the model is **enabled** in the AWS Bedrock console for your region. Claude 3.5 Sonnet requires explicit model access enablement.

### SQS messages piling up in DLQ

Check worker logs for the specific error (structured JSON logs include `error_type` and `document_url`). Common causes:
- PDF is password-protected or corrupt → manually remove from S3 and delete SQS message
- Bedrock throttling → increase `INGESTION_WORKER_CONCURRENCY` gradual backoff period
- Database connectivity → check security group ingress rules for Aurora port 5432

### OpenSearch `ConnectionError`

Confirm the `OPENSEARCH_HOST` setting matches the cluster endpoint (not the node endpoint). In VPC-mode OpenSearch, ensure the ECS task security group has egress to port 443 of the OpenSearch security group.

### `JWT expired` errors after deployment

Access tokens expire after 60 minutes. The frontend should automatically call `POST /auth/refresh` when it receives a `401` response. If the frontend is not refreshing, verify the `refresh_token` cookie/storage is being sent correctly.

### TypeScript build errors in `ui/`

```bash
cd ui
rm -rf node_modules
npm install
npx tsc --noEmit   # see specific type errors
```

### pgvector HNSW index not being used

Run `EXPLAIN ANALYZE` on a vector query. If a sequential scan is used instead of the HNSW index, the `enable_seqscan` GUC may be on or the table may be too small for the planner to choose the index. For tables < 1000 rows, the planner correctly chooses a seq scan.

---

## 17. Contributing

Contributions are welcome. Please follow these steps:

**1. Fork and branch**

```bash
git checkout -b feature/your-feature-name
```

**2. Install pre-commit hooks**

```bash
pip install pre-commit
pre-commit install
```

The hooks run `ruff`, `mypy`, and `tsc --noEmit` before each commit.

**3. Write tests**

- Unit tests go in `tests/unit/` — mock all external services
- Integration tests go in `tests/integration/` — require Docker Compose or real AWS

**4. Ensure CI passes locally**

```bash
pytest tests/unit/ -v           # all unit tests
cd ui && npx tsc --noEmit       # TypeScript
ruff check . && mypy .          # linting + types
```

**5. Open a pull request**

Describe:
- What the change does
- Why it is needed
- Any performance implications (especially for retrieval changes)
- Test coverage added

The CI pipeline will run automatically on your PR branch.

### Code Style

- Python: `ruff` (line length 100) + `mypy` strict where practical
- TypeScript: `strict: true` in `tsconfig.json`
- No `any` types without an explanatory comment
- All new Python code must be async-compatible

---

## 18. License

MIT License. See [LICENSE](LICENSE) for full text.

---

<details>
<summary><strong>Appendix: Key Model and Service Identifiers</strong></summary>

| Resource | Identifier |
|---|---|
| Embedding model | `amazon.titan-embed-text-v2:0` |
| LLM | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| Re-ranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| S3 raw bucket | `indyleg-raw-documents` |
| S3 processed bucket | `indyleg-processed-chunks` |
| OpenSearch index | `indyleg-legal-docs` |
| Vector dimension | `1024` |
| Chunk size | `512` characters |
| Chunk overlap | `64` characters |
| RRF smoothing constant | `60` |
| JWT access token TTL | `60 minutes` |
| JWT refresh token TTL | `7 days` |
| ECS baseline tasks | `2` |
| ECS max tasks | `6` |
| ECS CPU scale threshold | `70%` |

</details>

│  │                                                                      │    │
│  │  Query Parser ──▶ Embedding ──▶ Hybrid Search ──▶ Re-ranking        │    │
│  │  (jurisdiction,   (Bedrock      (pgvector +       (Cross-encoder     │    │
│  │   citations,       Titan v2)     BM25 + RRF)      ms-marco)         │    │
│  │   case type)                                                         │    │
│  └──────────────────────────┬──────────────────────────────────────────┘    │
│                             │                                               │
│  ┌──────────────────────────┴──────────────────────────────────────────┐    │
│  │                       GENERATION LAYER                               │    │
│  │                                                                      │    │
│  │  Prompt Builder ──▶ Bedrock Claude ──▶ Citation Validator            │    │
│  │  (citation-enforced   (temp=0.0,       (post-gen [SOURCE:] check,   │    │
│  │   system prompts)      auditable)       fallback on hallucination)   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       INGESTION LAYER                                │   │
│  │                                                                      │   │
│  │  Indiana Courts ──▶ SQS Queue ──▶ Worker Pool ──▶ pgvector + S3     │   │
│  │  API (Odyssey)      (batch +      (chunker +      (vectors +         │   │
│  │  + PDF/DOCX/HTML     DLQ)          embedder)       raw docs)         │   │
│  │                                                                      │   │
│  │  Structure-aware chunking: section boundaries, citation extraction,  │   │
│  │  sliding window (512 chars, 64 overlap), metadata enrichment         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       INFRASTRUCTURE (AWS)                           │   │
│  │                                                                      │   │
│  │  S3 (raw docs) │ SQS + DLQ │ Aurora pgvector │ OpenSearch │ ECS     │   │
│  │  Bedrock (Claude + Titan Embed v2) │ CloudWatch │ CDK (IaC)         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```text
Document ──▶ SQS ──▶ Worker ──▶ Parse ──▶ Chunk ──▶ Embed ──▶ pgvector
                                  │                              │
                                  ▼                              ▼
                                 S3 (raw)              BM25 index (OpenSearch)

User Query ──▶ Parse ──▶ Embed ──▶ Hybrid Search ──▶ Re-rank ──▶ Generate
               (jurisdiction,      (vector +           (cross-      (citation-
                citations)          BM25 + RRF)         encoder)     grounded)
```

---

## Project Structure

```text
indyleg/
├── config/              # Pydantic Settings, structured logging
├── ingestion/
│   ├── sources/         # Indiana courts API client, document parser
│   ├── pipeline/        # Chunker, Bedrock embedder, SQS worker
│   └── queue/           # SQS producer/consumer
├── retrieval/           # pgvector indexer, hybrid search, BM25, reranker, query parser
├── generation/          # Bedrock Claude client, prompts, citation validator
├── agents/              # Research & summarization agents (audit-logged)
├── api/                 # FastAPI app, routers, schemas, audit middleware
├── ui/                  # React + TypeScript + Vite frontend
├── infrastructure/
│   ├── cdk/             # AWS CDK stacks (ingestion + retrieval)
│   └── docker/          # Dockerfiles, init.sql
├── tests/
│   ├── unit/            # 19 unit tests
│   └── integration/     # Integration tests (Bedrock, pgvector, SQS)
└── .github/workflows/   # CI/CD pipeline
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for UI)
- Docker & Docker Compose
- AWS account with Bedrock access (Claude 3.5 Sonnet + Titan Embed v2)

### 1. Clone & Setup

```bash
git clone https://github.com/Anteneh-T-Tessema/legalairag.git
cd legalairag

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Environment variables
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

### 2. Start Local Services

```bash
# Start PostgreSQL (pgvector), OpenSearch, LocalStack
docker-compose up -d postgres opensearch localstack

# Wait for services to be ready (~15 seconds)
docker-compose logs -f postgres  # look for "ready to accept connections"
```

### 3. Run the API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at <http://localhost:8000/docs>

### 4. Run the UI

```bash
cd ui
npm install
npm run dev
```

UI available at <http://localhost:3000>

### 5. Start Ingestion Worker

```bash
python -m ingestion
```

---

## API Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/api/v1/search` | Hybrid vector + BM25 search with re-ranking |
| `POST` | `/api/v1/search/ask` | Full RAG: retrieve → re-rank → generate answer |
| `POST` | `/api/v1/documents/ingest` | Queue document for async ingestion |
| `GET` | `/health` | Health check |

### Example: Search

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "Indiana eviction notice requirements", "jurisdiction": "Marion County", "top_k": 5}'
```

### Example: Ask (RAG)

```bash
curl -X POST http://localhost:8000/api/v1/search/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query": "What are the filing deadlines for small claims in Indiana?"}'
```

---

## Running Tests

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests (requires local Docker services)
python -m pytest tests/integration/ -v --timeout=60

# All tests with coverage
python -m pytest --cov=. --cov-report=html
```

---

## AWS Deployment

### Deployment Prerequisites

- AWS CLI configured with appropriate IAM permissions
- AWS CDK v2 installed (`npm install -g aws-cdk`)
- Bedrock model access enabled in your AWS account

### Deploy

```bash
cd infrastructure/cdk
pip install aws-cdk-lib constructs
cdk bootstrap aws://ACCOUNT_ID/us-east-1
cdk deploy --all
```

---

## Key Design Decisions

| Decision | Rationale |
| -------- | --------- |
| **Hybrid retrieval (vector + BM25)** | Vector search for semantic recall; BM25 for precise legal citations. Fused via Reciprocal Rank Fusion. |
| **Structure-aware chunking** | Legal documents segmented by sections (facts, holdings, citations) rather than naive token windows. |
| **Citation grounding** | All generated answers require `[SOURCE: id]` markers validated against retrieved context. Hallucinated citations trigger fallback. |
| **Cross-encoder re-ranking** | ms-marco-MiniLM improves precision after initial hybrid retrieval over-fetch. |
| **Temperature 0.0** | Deterministic outputs required for government legal systems. |
| **Audit logging** | Every API request, agent action, and model call is logged with request_id for compliance traceability. |
| **Queue-based ingestion** | SQS decouples document intake from processing. DLQ catches failures. Backpressure via semaphore. |
| **JWT authentication** | Role-based access (admin, attorney, clerk) with token refresh rotation. |

---

## Tech Stack

- **Language**: Python 3.11, TypeScript
- **LLM**: AWS Bedrock (Claude 3.5 Sonnet)
- **Embeddings**: AWS Bedrock (Titan Embed Text v2, 1024 dims)
- **Vector DB**: PostgreSQL + pgvector
- **Keyword Search**: OpenSearch (BM25)
- **API**: FastAPI
- **UI**: React + Vite + TypeScript
- **Infrastructure**: AWS CDK, Docker, ECS Fargate
- **CI/CD**: GitHub Actions

---

## License

Proprietary — State of Indiana.
