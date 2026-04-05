"""Unit tests for IngestionWorker content-hash deduplication logic.

All external collaborators (S3, SQS, Bedrock, VectorIndexer, LegalChunker) are
mocked so the tests run offline without any cloud credentials.

psycopg is mocked at sys.modules level before any import that transitively
pulls it in, because the local PostgreSQL install is x86_64 and psycopg requires
an arm64 libpq on Apple Silicon.
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock psycopg and pgvector before they are imported by retrieval.indexer.
# This avoids the architecture mismatch error on Apple Silicon.
# ---------------------------------------------------------------------------
_psycopg_mock = types.ModuleType("psycopg")
_psycopg_mock.AsyncConnection = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("psycopg", _psycopg_mock)

_pgvector_mock = types.ModuleType("pgvector")
_pgvector_psycopg_mock = types.ModuleType("pgvector.psycopg")
_pgvector_psycopg_mock.register_vector = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("pgvector", _pgvector_mock)
sys.modules.setdefault("pgvector.psycopg", _pgvector_psycopg_mock)
# ---------------------------------------------------------------------------

from ingestion.pipeline.worker import IngestionWorker  # noqa: E402
from ingestion.queue.sqs import IngestionMessage  # noqa: E402

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_message(source_id: str = "src-001") -> IngestionMessage:
    return IngestionMessage(
        source_type="indiana_courts",
        source_id=source_id,
        download_url="https://example.com/doc.pdf",
        metadata={"jurisdiction": "indiana"},
    )


def _make_worker() -> IngestionWorker:
    """Construct an IngestionWorker with all external I/O mocked out."""
    with (
        patch("ingestion.pipeline.worker.SQSConsumer"),
        patch("ingestion.pipeline.worker.BedrockEmbedder"),
        patch("ingestion.pipeline.worker.LegalChunker"),
        patch("ingestion.pipeline.worker.VectorIndexer"),
        patch("ingestion.pipeline.worker.boto3"),
    ):
        worker = IngestionWorker.__new__(IngestionWorker)
        worker._concurrency = 1
        worker._semaphore = asyncio.Semaphore(1)
        worker._chunker = MagicMock()
        worker._embedder = MagicMock()
        worker._indexer = MagicMock()
        worker._s3 = MagicMock()
        worker._consumer = MagicMock()
        return worker


# ── Deduplication (core logic) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unchanged_document_skips_embedding():
    """If record_version returns is_new_version=False, upsert_batch must NOT run."""
    worker = _make_worker()
    message = _make_message()

    # _download returns some bytes
    worker._download = AsyncMock(return_value=b"pdf content unchanged")

    # Simulate: same content hash already in DB
    worker._indexer.record_version = AsyncMock(return_value=("ver-abc@123", False))
    worker._indexer.upsert_batch = AsyncMock()
    worker._chunker.chunk = MagicMock(return_value=[])
    worker._embedder.embed_chunks = AsyncMock(return_value=[])

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process(message)

    worker._indexer.record_version.assert_awaited_once()
    worker._indexer.upsert_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_document_triggers_embedding():
    """If record_version returns is_new_version=True, the full pipeline runs."""
    worker = _make_worker()
    message = _make_message()

    worker._download = AsyncMock(return_value=b"new pdf content")
    worker._indexer.record_version = AsyncMock(return_value=("ver-xyz@456", True))
    worker._indexer.upsert_batch = AsyncMock()

    fake_chunk = MagicMock()
    worker._chunker.chunk = MagicMock(return_value=[fake_chunk])
    worker._embedder.embed_chunks = AsyncMock(return_value=[(fake_chunk, [0.1, 0.2])])

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process(message)

    worker._indexer.upsert_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_version_called_with_source_id():
    """record_version must always be called even for unchanged docs."""
    worker = _make_worker()
    message = _make_message(source_id="my-unique-source")

    worker._download = AsyncMock(return_value=b"content")
    worker._indexer.record_version = AsyncMock(return_value=("v1", False))
    worker._indexer.upsert_batch = AsyncMock()
    worker._chunker.chunk = MagicMock(return_value=[])
    worker._embedder.embed_chunks = AsyncMock(return_value=[])

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process(message)

    call_kwargs = worker._indexer.record_version.call_args.kwargs
    assert call_kwargs["source_id"] == "my-unique-source"


@pytest.mark.asyncio
async def test_process_with_ack_deletes_on_success():
    """Successful processing should delete the SQS message."""
    worker = _make_worker()
    message = _make_message()

    worker._download = AsyncMock(return_value=b"content")
    worker._indexer.record_version = AsyncMock(return_value=("v1", False))
    worker._indexer.upsert_batch = AsyncMock()
    worker._consumer.delete = AsyncMock()

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process_with_ack(message, receipt_handle="receipt-abc")

    worker._consumer.delete.assert_awaited_once_with("receipt-abc")


@pytest.mark.asyncio
async def test_process_with_ack_does_not_delete_on_failure():
    """On failure the SQS message is NOT deleted — SQS handles redelivery."""
    worker = _make_worker()
    message = _make_message()

    worker._download = AsyncMock(side_effect=RuntimeError("S3 down"))
    worker._consumer.delete = AsyncMock()

    await worker._process_with_ack(message, receipt_handle="receipt-xyz")

    worker._consumer.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_chunks_passed_to_embedder():
    """All chunks produced by the chunker must be sent to the embedder."""
    worker = _make_worker()
    message = _make_message()

    chunk_a = MagicMock()
    chunk_b = MagicMock()
    worker._download = AsyncMock(return_value=b"doc")
    worker._indexer.record_version = AsyncMock(return_value=("v1", True))
    worker._chunker.chunk = MagicMock(return_value=[chunk_a, chunk_b])
    worker._embedder.embed_chunks = AsyncMock(return_value=[(chunk_a, [0.1]), (chunk_b, [0.2])])
    worker._indexer.upsert_batch = AsyncMock()

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process(message)

    worker._embedder.embed_chunks.assert_awaited_once_with([chunk_a, chunk_b])


@pytest.mark.asyncio
async def test_empty_chunks_calls_upsert_with_empty_list():
    """Zero chunks from the chunker → upsert_batch called with []."""
    worker = _make_worker()
    message = _make_message()

    worker._download = AsyncMock(return_value=b"empty doc")
    worker._indexer.record_version = AsyncMock(return_value=("v1", True))
    worker._chunker.chunk = MagicMock(return_value=[])
    worker._embedder.embed_chunks = AsyncMock(return_value=[])
    worker._indexer.upsert_batch = AsyncMock()

    with patch("ingestion.pipeline.worker.load_from_bytes") as mock_load:
        mock_load.return_value = MagicMock()
        await worker._process(message)

    worker._indexer.upsert_batch.assert_awaited_once_with([])
