"""Integration tests for retrieval.indexer.VectorIndexer.

These tests require a running PostgreSQL instance with the pgvector extension.
They are gated behind the ``TEST_DATABASE_URL`` environment variable, which must
point to a writable test database.

Run locally:
    TEST_DATABASE_URL="postgresql://user:pass@localhost/indyleg_test" pytest tests/integration/test_pgvector.py -v

In CI the tests are automatically skipped when the variable is absent.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any

import pytest

from ingestion.pipeline.chunker import Chunk
from retrieval.indexer import VectorIndexer

# ── Skip guard ────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping pgvector integration tests",
)

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk(
    source_id: str,
    text: str = "Indiana Code § 35-42-1-1",
    section: str = "§ 35-42-1-1",
) -> Chunk:
    chunk_id = str(uuid.uuid4())
    return Chunk(
        chunk_id=chunk_id,
        source_id=source_id,
        text=text,
        section_header=section,
        section_index=0,
        char_start=0,
        char_end=len(text),
        citations=["35-42-1-1"],
        metadata={"jurisdiction": "indiana"},
    )


def _vector(dim: int = 1536) -> list[float]:
    return [0.01] * dim


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
async def indexer():
    idx = VectorIndexer(database_url=TEST_DB_URL)
    yield idx
    await idx.close()


# ── upsert_batch ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_single_chunk_no_error(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    chunk = _chunk(source_id)
    await indexer.upsert_batch([(chunk, _vector())])


@pytest.mark.asyncio
async def test_upsert_idempotent(indexer: VectorIndexer):
    """Upserting the same chunk twice must not raise."""
    source_id = f"test-{uuid.uuid4()}"
    chunk = _chunk(source_id)
    vec = _vector()
    await indexer.upsert_batch([(chunk, vec)])
    await indexer.upsert_batch([(chunk, vec)])  # idempotent


@pytest.mark.asyncio
async def test_delete_source_removes_chunks(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    chunks = [_chunk(source_id, text=f"text {i}") for i in range(3)]
    await indexer.upsert_batch([(c, _vector()) for c in chunks])
    deleted = await indexer.delete_source(source_id)
    assert deleted == 3


@pytest.mark.asyncio
async def test_delete_unknown_source_returns_zero(indexer: VectorIndexer):
    deleted = await indexer.delete_source("nonexistent-source-xyz")
    assert deleted == 0


# ── record_version ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_version_first_call_is_new(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    _, is_new = await indexer.record_version(
        source_id=source_id,
        content="first version content",
        metadata={},
    )
    assert is_new is True


@pytest.mark.asyncio
async def test_record_version_identical_content_not_new(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    content = "identical content"
    await indexer.record_version(source_id=source_id, content=content, metadata={})
    _, is_new = await indexer.record_version(
        source_id=source_id,
        content=content,
        metadata={},
    )
    assert is_new is False


@pytest.mark.asyncio
async def test_record_version_changed_content_is_new(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    await indexer.record_version(
        source_id=source_id,
        content="original",
        metadata={},
    )
    _, is_new = await indexer.record_version(
        source_id=source_id,
        content="amended — content changed",
        metadata={},
    )
    assert is_new is True


@pytest.mark.asyncio
async def test_record_version_returns_deterministic_id(indexer: VectorIndexer):
    source_id = f"test-{uuid.uuid4()}"
    content = "stable content string"
    version_id_1, _ = await indexer.record_version(
        source_id=source_id, content=content, metadata={}
    )
    hash_prefix = hashlib.sha256(content.encode()).hexdigest()[:12]
    assert version_id_1 == f"{source_id}@{hash_prefix}"


@pytest.mark.asyncio
async def test_upsert_empty_batch_no_error(indexer: VectorIndexer):
    await indexer.upsert_batch([])
