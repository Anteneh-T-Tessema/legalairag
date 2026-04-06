# Testing Guide

**Version**: 0.7.0 | **Date**: April 2026

This document describes the IndyLeg test strategy, how to run tests, and how to write new ones.

---

## Test Structure

```text
tests/
├── data/
│   └── eval_queries.json               # Ground-truth evaluation dataset
├── unit/                               # Fast, isolated, all mocked
│   ├── test_api_auth.py                # Auth endpoints, JWT tokens, RBAC
│   ├── test_api_documents.py           # Document ingestion endpoint
│   ├── test_api_fraud.py               # Fraud analysis endpoint
│   ├── test_api_main.py                # App startup, health, metrics, CORS
│   ├── test_api_search.py              # Search & ask endpoints
│   ├── test_authority.py               # Court hierarchy + alpha blending
│   ├── test_base_agent.py              # BaseAgent framework, audit trail
│   ├── test_bedrock_client.py          # Bedrock embedding/generation client
│   ├── test_chunker.py                 # Legal-aware chunking
│   ├── test_cli.py                     # Ingestion CLI entry point
│   ├── test_document_loader.py         # Document source loading
│   ├── test_ecosystem_clients.py       # Indiana courts ecosystem clients
│   ├── test_embedder.py                # Embedding pipeline
│   ├── test_evaluator.py               # IR metrics (recall, precision, MRR, NDCG)
│   ├── test_fraud_detection.py         # All 5 fraud detectors + risk scoring
│   ├── test_generator.py               # Prompt assembly, citation injection
│   ├── test_hybrid_search.py           # RRF fusion formula
│   ├── test_indiana_courts.py          # Indiana courts data source
│   ├── test_indexer.py                 # pgvector indexer operations
│   ├── test_ingestion_init.py          # Ingestion module init
│   ├── test_legal_qa.py                # Legal QA prompt templates
│   ├── test_logging.py                 # Logging configuration
│   ├── test_middleware.py              # Rate limit, audit, metrics, security headers
│   ├── test_mycase_client.py           # MyCase integration client
│   ├── test_public_resource.py         # Public resource loader
│   ├── test_query_parser.py            # Query parsing & jurisdiction detection
│   ├── test_reranker.py                # Cross-encoder re-ranking
│   ├── test_research_agent.py          # CaseResearchAgent 6-step pipeline
│   ├── test_secrets.py                 # Secrets management
│   ├── test_settings.py                # Application settings
│   ├── test_sqs.py                     # SQS queue unit tests
│   ├── test_summarization_agent.py     # SummarizationAgent
│   └── test_validator.py               # Response validation
├── integration/                        # Require running services (Docker Compose)
│   ├── test_sqs.py                     # SQS produce/consume via LocalStack
│   ├── test_bedrock.py                 # Live Bedrock embedding + generation
│   └── test_pgvector.py                # pgvector insert + cosine search
├── performance/
│   └── test_benchmarks.py              # Latency and throughput benchmarks
└── e2e/                                # Full pipeline, mocked boundaries
    ├── test_rag_pipeline.py            # Full RAG pipeline end-to-end
    └── test_live_pipeline.py           # Live pipeline integration
```

---

## Running Tests

### Unit Tests (no external services needed)

```bash
# All unit tests
pytest tests/unit/ -v

# Single test file
pytest tests/unit/test_fraud_detection.py -v

# Single test
pytest tests/unit/test_authority.py::test_authority_rerank_blending -v
```

### Integration Tests

These require Docker Compose services or real AWS credentials:

```bash
# Start local services first
docker compose up -d

# SQS tests (uses LocalStack)
pytest tests/integration/test_sqs.py -v

# pgvector tests (requires PostgreSQL with pgvector extension)
pytest tests/integration/test_pgvector.py -v

# Bedrock tests (requires real AWS credentials + model access)
pytest tests/integration/test_bedrock.py -v
```

### End-to-End Tests

```bash
pytest tests/e2e/ -v
```

### Full Suite with Coverage

```bash
pytest --cov=. --cov-report=html --cov-report=term-missing tests/
open htmlcov/index.html
```

### UI Tests

```bash
cd ui && npm run test
```

---

## Test Coverage Summary

**712 tests — all passing — 100% code coverage**

| Category | Test Files | Tests | Notes |
|---|---|---|---|
| Unit | 34 | ~660 | All external services mocked |
| Integration | 3 | ~22 | SQS (LocalStack), pgvector, Bedrock |
| Performance | 1 | ~5 | Latency benchmarks |
| E2E | 2 | ~25 | Full pipeline with mocked Bedrock |
| **Total Python** | **40** | **712** | **100% line + branch coverage** |
| UI (vitest) | 7 | 54 | React components + API client |

### Unit Test Details

| Test File | What It Covers |
|---|---|
| `test_api_auth.py` | JWT token creation/verification, login/logout/refresh, HMAC-SHA256 password hashing, RBAC role checks, token blacklisting, expiry |
| `test_api_documents.py` | Document ingestion endpoint, auth requirements, request validation |
| `test_api_fraud.py` | Fraud analysis endpoint, auth + role validation, response schema |
| `test_api_main.py` | FastAPI app startup, `/health`, `/metrics`, `/metrics/json`, CORS, middleware stack |
| `test_api_search.py` | `/search` and `/search/ask`, query validation, jurisdiction filtering |
| `test_authority.py` | All court hierarchy weights, default weight, alpha blending, temporal validity, stale doc filtering |
| `test_base_agent.py` | BaseAgent lifecycle, tool access control, audit trail, error handling, run metadata |
| `test_bedrock_client.py` | Bedrock Titan embedding, Claude generation, token counting, error handling |
| `test_chunker.py` | Section boundary detection (§, ARTICLE, SECTION), sliding window overlap, citation extraction, metadata enrichment |
| `test_cli.py` | CLI argument parsing, ingestion pipeline entry point |
| `test_document_loader.py` | S3 document loading, format detection, content extraction |
| `test_ecosystem_clients.py` | Indiana courts ecosystem API clients |
| `test_embedder.py` | Batch embedding pipeline, dimension validation, error recovery |
| `test_evaluator.py` | Recall@K, Precision@K, MRR, NDCG, citation accuracy, faithfulness, edge cases |
| `test_fraud_detection.py` | Burst filing, identity reuse, deed fraud, suspicious entities, rapid ownership transfer, risk aggregation |
| `test_generator.py` | System prompt construction, context formatting, Bedrock mocking, response parsing |
| `test_hybrid_search.py` | RRF score computation, zero-score edges, result ordering, empty result sets |
| `test_indiana_courts.py` | Indiana courts data source, case type codes, API response parsing |
| `test_indexer.py` | pgvector table creation, upsert, search, IVFFlat index management |
| `test_ingestion_init.py` | Ingestion module initialization and exports |
| `test_legal_qa.py` | Legal QA prompt templates, jurisdiction-specific prompts |
| `test_logging.py` | Structured JSON logging configuration, log levels |
| `test_middleware.py` | Rate limiting, audit log, metrics collection, security headers (CSP, HSTS) |
| `test_mycase_client.py` | MyCase API integration client |
| `test_public_resource.py` | Public resource document loader |
| `test_query_parser.py` | Query parsing, jurisdiction detection, citation extraction, case type classification |
| `test_reranker.py` | Cross-encoder re-ranking, score normalization, top-K selection |
| `test_research_agent.py` | CaseResearchAgent 6-step pipeline: parse → embed → search → rerank → authority-blend → generate |
| `test_secrets.py` | AWS Secrets Manager integration, fallback to env vars |
| `test_settings.py` | Settings loading from env, defaults, validation |
| `test_sqs.py` | SQS message send/receive, batch operations, error handling |
| `test_summarization_agent.py` | SummarizationAgent pipeline, output formatting |
| `test_validator.py` | Response validation, citation checking, confidence estimation |

### Integration Test Details

| Test File | What It Covers |
|---|---|
| `test_sqs.py` | End-to-end SQS enqueue/dequeue via LocalStack, batch send |
| `test_bedrock.py` | Real Bedrock Titan Embed (1024-dim vector), Claude generation, token counting |
| `test_pgvector.py` | Vector insert, cosine similarity search, metadata filtering, IVFFlat index |

### End-to-End Test Details

| Test File | What It Covers |
|---|---|
| `test_rag_pipeline.py` | Full 6-step pipeline with mocked Bedrock: parse → embed → search → rerank → authority-blend → generate → validate |
| `test_live_pipeline.py` | Live pipeline integration with running services |

---

## Writing New Tests

### Unit Test Conventions

- Place in `tests/unit/`
- Mock all external services (Bedrock, PostgreSQL, OpenSearch, SQS)
- Use `pytest-asyncio` for async tests (auto mode configured in `pyproject.toml`)
- Name test functions `test_<what_it_tests>`
- Group related tests in classes if they share fixtures
- Maintain 100% code coverage — new code must include tests

### Example Test

```python
import pytest
from retrieval.authority import AuthorityRanker, get_authority_score
from retrieval.hybrid_search import SearchResult

def test_indiana_supreme_court_weight():
    """Indiana Supreme Court should have weight 0.85."""
    assert get_authority_score("Indiana Supreme Court") == 0.85

def test_unknown_court_gets_default_weight():
    """Courts not in the hierarchy should get the default weight."""
    assert get_authority_score("Some Random Court") == 0.35

def test_authority_rerank_blending():
    """AuthorityRanker should blend retrieval scores with authority scores."""
    ranker = AuthorityRanker(authority_alpha=0.30)
    results = [
        SearchResult(chunk_id="c1", content="...", source_id="s1", score=0.90,
                     metadata={"court": "Indiana Trial Court"}),
        SearchResult(chunk_id="c2", content="...", source_id="s2", score=0.70,
                     metadata={"court": "Indiana Supreme Court"}),
    ]
    reranked = ranker.rerank(results)
    # Supreme Court result should be boosted
    assert reranked[0].chunk_id == "c2"
```

### Fixture Tips

- Use `@pytest.fixture` for shared setup (mock embedder, mock searcher)
- Use `conftest.py` for project-wide fixtures
- For `SearchResult` objects, provide minimal but realistic metadata
- For fraud detection tests, build `SearchResult` lists with specific metadata patterns

---

## Linting and Type Checking

```bash
# Python linting (ruff)
ruff check .
ruff format --check .

# Type checking (Pyright — basic mode)
pyright

# TypeScript type checking
cd ui && npx tsc --noEmit
```

### Ruff Configuration

Configured in `pyproject.toml`:
- Line length: 100
- Rules: E, F, I, UP, B, S
- Ignored: S101 (assert in tests), B008, S608, UP017
- Per-file ignores for test files: S101, S105, S106

### Coverage Configuration

Configured in `pyproject.toml`:
- `fail_under = 100` — CI will fail if coverage drops below 100%
- Source packages: `agents`, `api`, `config`, `generation`, `ingestion`, `retrieval`
- Excludes: `tests/*`, `infrastructure/*`, `*/__main__.py`
