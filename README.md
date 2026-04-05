# IndyLeg — Indiana Legal RAG Platform

AI-powered legal research and document intelligence for Indiana courts. A production-grade Retrieval-Augmented Generation (RAG) system built on AWS Bedrock, designed for non-technical legal staff.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INDIANA LEGAL RAG PLATFORM                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│  │  React UI    │───▶│  FastAPI      │───▶│  Agent Layer                 │  │
│  │  (Vite+TS)   │    │  /api/v1      │    │  ┌─────────────────────────┐│  │
│  │              │◀───│              │◀───│  │ Research Agent          ││  │
│  │ • Search     │    │ • /search    │    │  │ Summarization Agent     ││  │
│  │ • Chat       │    │ • /search/ask│    │  │ (audit-logged, tool-    ││  │
│  │ • Documents  │    │ • /documents │    │  │  controlled)            ││  │
│  │ • Viewer     │    │ • /health    │    │  └─────────────────────────┘│  │
│  └──────────────┘    └──────┬───────┘    └──────────────┬───────────────┘  │
│                             │                           │                   │
│  ┌──────────────────────────┴───────────────────────────┘                   │
│  │                                                                          │
│  ▼                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       RETRIEVAL LAYER                                │    │
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
