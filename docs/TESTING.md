# Testing Guide

This document describes the IndyLeg test strategy, how to run tests, and how to write new ones.

---

## Test Structure

```text
tests/
├── data/
│   └── eval_queries.json           # Ground-truth evaluation dataset
├── unit/                           # Fast, isolated, all mocked
│   ├── test_chunker.py             # Legal-aware chunking
│   ├── test_hybrid_search.py       # RRF fusion formula
│   ├── test_generator.py           # Prompt assembly, citation injection
│   ├── test_authority.py           # Court hierarchy + alpha blending
│   ├── test_evaluator.py           # IR metrics (recall, precision, MRR, NDCG)
│   ├── test_fraud_detection.py     # All 5 fraud detectors + risk scoring
│   └── test_worker.py              # Dedup, message processing
├── integration/                    # Require running services (Docker Compose)
│   ├── test_sqs.py                 # SQS produce/consume via moto mock
│   ├── test_bedrock.py             # Live Bedrock embedding + generation
│   └── test_pgvector.py            # pgvector insert + cosine search
└── e2e/                            # Full pipeline, mocked boundaries
    └── test_rag_pipeline.py        # parse → embed → search → rerank → generate
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

# SQS tests (uses moto — no real AWS needed)
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

---

## Test Coverage Summary

**141 tests — all passing**

### Unit Test Details

| Test File | Tests | What It Covers |
|---|---|---|
| `test_chunker.py` | Section boundary detection (§, ARTICLE, SECTION headings), sliding window overlap, Indiana Code citation extraction, empty/short input handling, metadata enrichment |
| `test_hybrid_search.py` | RRF score computation, zero-score edge case (division by k+rank not k+0), result ordering after fusion, empty result sets from one or both retrievers |
| `test_generator.py` | System prompt construction with citation enforcement, context chunk formatting, Bedrock API call mocking, response parsing |
| `test_authority.py` | All court hierarchy weights (exact + substring match), default weight for unknown courts, alpha blending formula, temporal validity (effective/expiry dates), stale document filtering |
| `test_evaluator.py` | Recall@K at various K values, Precision@K, Mean Reciprocal Rank, NDCG with graded relevance, citation accuracy with hallucinated citations, faithfulness scoring with legal terms, edge cases (empty sets, perfect scores) |
| `test_fraud_detection.py` | Burst filing with sliding 30-day window, identity reuse (SSN, DOB, address), deed fraud (quitclaim + nominal consideration), suspicious entities (numeric names), rapid ownership transfer (90-day window), risk level aggregation, no-indicator case |
| `test_worker.py` | Content-hash deduplication, SQS message parsing, chunk + embed pipeline flow, error handling for corrupt documents |

### Integration Test Details

| Test File | What It Covers |
|---|---|
| `test_sqs.py` | End-to-end SQS enqueue/dequeue cycle using moto mock, batch send, DLQ behavior |
| `test_bedrock.py` | Real Bedrock Titan Embed call (produces 1024-dim vector), Claude generation call, token counting |
| `test_pgvector.py` | Vector insert, cosine similarity search, metadata filtering, HNSW index usage |

### End-to-End Test Details

| Test File | What It Covers |
|---|---|
| `test_rag_pipeline.py` | Full 5-step pipeline with mocked Bedrock: query parsing → embedding → hybrid search → authority reranking → generation → citation validation |

---

## Writing New Tests

### Unit Test Conventions

- Place in `tests/unit/`
- Mock all external services (Bedrock, PostgreSQL, OpenSearch, SQS)
- Use `pytest-asyncio` for async tests (auto mode configured in `pyproject.toml`)
- Name test functions `test_<what_it_tests>`
- Group related tests in classes if they share fixtures

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

# Type checking (Pyright)
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
