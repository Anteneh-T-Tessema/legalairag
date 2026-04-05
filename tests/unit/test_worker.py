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


# ── Download helpers ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_s3_calls_get_object_with_correct_bucket_and_key():
    """_download_s3 parses s3://bucket/key and calls get_object correctly."""
    worker = _make_worker()
    fake_body = MagicMock()
    fake_body.read.return_value = b"pdf content from s3"
    worker._s3.get_object.return_value = {"Body": fake_body}

    result = await worker._download_s3("s3://my-bucket/legal/documents/statute.pdf")

    worker._s3.get_object.assert_called_once_with(
        Bucket="my-bucket", Key="legal/documents/statute.pdf"
    )
    assert result == b"pdf content from s3"


@pytest.mark.asyncio
async def test_download_s3_returns_bytes():
    """_download_s3 casts the S3 body to bytes."""
    worker = _make_worker()
    fake_body = MagicMock()
    fake_body.read.return_value = b"\x00\x01\x02binary"
    worker._s3.get_object.return_value = {"Body": fake_body}

    result = await worker._download_s3("s3://bucket/key.pdf")
    assert isinstance(result, bytes)


@pytest.mark.asyncio
async def test_download_http_returns_response_content():
    """_download_http fetches URL and returns resp.content."""

    worker = _make_worker()

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.content = b"html legal document"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await worker._download_http("https://iga.in.gov/laws/2024/statute.pdf")

    fake_resp.raise_for_status.assert_called_once()
    assert result == b"html legal document"


@pytest.mark.asyncio
async def test_download_http_raises_on_bad_status():
    """_download_http propagates raise_for_status errors."""
    import httpx

    worker = _make_worker()

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await worker._download_http("https://example.com/missing.pdf")


@pytest.mark.asyncio
async def test_download_dispatches_to_s3_for_s3_upload_source():
    """_download routes s3_upload messages to _download_s3."""
    worker = _make_worker()
    s3_message = IngestionMessage(
        source_type="s3_upload",
        source_id="doc-s3",
        download_url="s3://bucket/doc.pdf",
        metadata={},
    )
    worker._download_s3 = AsyncMock(return_value=b"s3 bytes")
    worker._download_http = AsyncMock(return_value=b"http bytes")

    await worker._download(s3_message)

    worker._download_s3.assert_awaited_once_with("s3://bucket/doc.pdf")
    worker._download_http.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_dispatches_to_http_for_non_s3_source():
    """_download routes non-s3 messages to _download_http."""
    worker = _make_worker()
    http_message = IngestionMessage(
        source_type="indiana_courts",
        source_id="doc-http",
        download_url="https://courts.in.gov/doc.pdf",
        metadata={},
    )
    worker._download_s3 = AsyncMock(return_value=b"s3 bytes")
    worker._download_http = AsyncMock(return_value=b"http bytes")

    await worker._download(http_message)

    worker._download_http.assert_awaited_once_with("https://courts.in.gov/doc.pdf")
    worker._download_s3.assert_not_awaited()


# ── IngestionWorker.__init__ ────────────────────────────────────────────────────


def test_ingestion_worker_init_creates_all_dependencies():
    """Cover lines 39-45: __init__ body instantiates all collaborators."""
    with (
        patch("ingestion.pipeline.worker.SQSConsumer") as mock_sqs,
        patch("ingestion.pipeline.worker.BedrockEmbedder") as mock_emb,
        patch("ingestion.pipeline.worker.LegalChunker") as mock_chunker,
        patch("ingestion.pipeline.worker.VectorIndexer") as mock_indexer,
        patch("ingestion.pipeline.worker.boto3") as mock_boto,
        patch("ingestion.pipeline.worker.settings") as mock_settings,
    ):
        mock_settings.ingestion_worker_concurrency = 2
        mock_settings.aws_region = "us-east-1"

        worker = IngestionWorker(concurrency=2)

    assert worker._concurrency == 2
    mock_chunker.assert_called_once()
    mock_emb.assert_called_once()
    mock_indexer.assert_called_once()
    mock_boto.client.assert_called_once()
    mock_sqs.assert_called_once()


# ── IngestionWorker.run() ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_creates_tasks_for_each_message():
    """Cover lines 49-55: run() spawns a task per message and registers discard callback."""
    worker = _make_worker()
    worker._concurrency = 4  # high to avoid backpressure in this test
    worker._semaphore = asyncio.Semaphore(4)
    worker._process_with_ack = AsyncMock()

    msg = _make_message()

    async def _one_message():
        yield msg, "rh-run-1"

    worker._consumer.receive = _one_message
    await worker.run()
    # With concurrency=4, there's no backpressure wait, so the task is scheduled
    # but may not have fully run. Verify the coroutine was at least called.
    assert worker._process_with_ack.call_count == 1


@pytest.mark.asyncio
async def test_run_applies_backpressure_when_at_concurrency():
    """Cover lines 58-59: backpressure wait fires when tasks == concurrency."""
    worker = _make_worker()
    worker._concurrency = 1  # so backpressure fires after first message
    worker._semaphore = asyncio.Semaphore(1)
    worker._process_with_ack = AsyncMock()

    msg = _make_message()

    async def _one_message():
        yield msg, "rh-bp-1"

    worker._consumer.receive = _one_message
    await worker.run()
    worker._process_with_ack.assert_awaited_once_with(msg, "rh-bp-1")


@pytest.mark.asyncio
async def test_run_with_empty_receive_returns_immediately():
    """Cover 52->exit: run() exits cleanly when the consumer yields no messages."""
    worker = _make_worker()
    worker._process_with_ack = AsyncMock()

    async def _no_messages():
        return
        yield  # make it an async generator

    worker._consumer.receive = _no_messages
    await worker.run()
    worker._process_with_ack.assert_not_awaited()
