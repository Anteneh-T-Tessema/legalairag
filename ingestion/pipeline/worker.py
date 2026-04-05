from __future__ import annotations

import asyncio
from typing import Any

import boto3

from config.settings import settings
from config.logging import get_logger
from ingestion.pipeline.chunker import Chunk, LegalChunker
from ingestion.pipeline.embedder import BedrockEmbedder
from ingestion.queue.sqs import IngestionMessage, SQSConsumer
from ingestion.sources.document_loader import load_from_bytes
from retrieval.indexer import VectorIndexer

logger = get_logger(__name__)


class IngestionWorker:
    """
    SQS-driven ingestion worker.

    Pipeline per message:
      1. Download document bytes from S3 or direct URL
      2. Parse (PDF/DOCX/HTML)
      3. Structure-aware chunk
      4. Batch embed via Bedrock
      5. Upsert into vector store + OpenSearch BM25 index

    Independent pipeline stages run concurrently where possible.
    Each stage is connected via in-memory queues within the worker process;
    at scale, these become separate workers consuming separate SQS queues.
    """

    def __init__(
        self,
        concurrency: int = settings.ingestion_worker_concurrency,
    ) -> None:
        self._concurrency = concurrency
        self._chunker = LegalChunker()
        self._embedder = BedrockEmbedder()
        self._indexer = VectorIndexer()
        self._s3 = boto3.client("s3", region_name=settings.aws_region)
        self._consumer = SQSConsumer()
        self._semaphore = asyncio.Semaphore(concurrency)

    async def run(self) -> None:
        """Start consuming messages indefinitely."""
        logger.info("worker_starting", concurrency=self._concurrency)
        tasks: set[asyncio.Task[None]] = set()

        async for message, receipt_handle in self._consumer.receive():
            task = asyncio.create_task(
                self._process_with_ack(message, receipt_handle)
            )
            tasks.add(task)
            task.add_done_callback(tasks.discard)

            # Backpressure: wait when at max concurrency
            if len(tasks) >= self._concurrency:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    async def _process_with_ack(
        self, message: IngestionMessage, receipt_handle: str
    ) -> None:
        async with self._semaphore:
            try:
                await self._process(message)
                await self._consumer.delete(receipt_handle)
                logger.info("ingestion_success", source_id=message.source_id)
            except Exception as exc:
                logger.error(
                    "ingestion_failure",
                    source_id=message.source_id,
                    error=str(exc),
                    exc_info=True,
                )
                # Leave message in queue; SQS will redeliver or route to DLQ

    async def _process(self, message: IngestionMessage) -> None:
        content, metadata = await asyncio.gather(
            self._download(message),
            asyncio.sleep(0, result=message.metadata),  # passthrough metadata
        )

        doc = load_from_bytes(
            content=content,
            source_id=message.source_id,
            filename=_filename_from_url(message.download_url),
            metadata=metadata,
        )

        # Content-hash deduplication: skip embedding if document is unchanged.
        # record_version() returns is_new_version=False when the content hash
        # matches the last ingested version, preventing redundant Bedrock calls.
        _version_id, is_new_version = await self._indexer.record_version(
            source_id=message.source_id,
            content=content,
            metadata=metadata,
        )
        if not is_new_version:
            logger.info("skipping_unchanged_document", source_id=message.source_id)
            return

        chunks = self._chunker.chunk(doc)
        logger.info("chunks_created", source_id=message.source_id, count=len(chunks))

        embedded = await self._embedder.embed_chunks(chunks)
        await self._indexer.upsert_batch(embedded)

    async def _download(self, message: IngestionMessage) -> bytes:
        if message.source_type == "s3_upload":
            return await self._download_s3(message.download_url)
        return await self._download_http(message.download_url)

    async def _download_s3(self, s3_uri: str) -> bytes:
        # s3_uri format: s3://bucket/key
        parts = s3_uri.removeprefix("s3://").split("/", 1)
        bucket, key = parts[0], parts[1]
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._s3.get_object(Bucket=bucket, Key=key),
        )
        return response["Body"].read()  # type: ignore[return-value]

    async def _download_http(self, url: str) -> bytes:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content


def _filename_from_url(url: str) -> str:
    from urllib.parse import urlparse

    path = urlparse(url).path
    return path.split("/")[-1] or "document.bin"
