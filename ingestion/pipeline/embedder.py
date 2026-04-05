from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.config import Config

from config.logging import get_logger
from config.settings import settings
from ingestion.pipeline.chunker import Chunk

logger = get_logger(__name__)

_BEDROCK_CONFIG = Config(
    region_name=settings.aws_region,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


class BedrockEmbedder:
    """
    Batch embedder using AWS Bedrock Titan Embed v2.

    Key design decisions:
    - Batches chunks (default 128 per call) to maximise throughput and minimise cost.
    - Runs embedding calls concurrently with a configurable semaphore.
    - Each embedding call is synchronous boto3 wrapped in a thread pool — Bedrock
      does not yet expose a true async API.
    """

    def __init__(
        self,
        model_id: str = settings.bedrock_embedding_model,
        batch_size: int = settings.embedding_batch_size,
        max_concurrent_batches: int = 4,
    ) -> None:
        self._model_id = model_id
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(max_concurrent_batches)
        self._client = boto3.client("bedrock-runtime", config=_BEDROCK_CONFIG)

    async def embed_chunks(self, chunks: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
        """
        Embed a list of chunks and return (chunk, embedding) pairs.
        Batches automatically; concurrent batch execution is bounded by the semaphore.
        """
        batches = [
            chunks[i : i + self._batch_size] for i in range(0, len(chunks), self._batch_size)
        ]
        logger.info(
            "embedding_batches",
            total_chunks=len(chunks),
            num_batches=len(batches),
            batch_size=self._batch_size,
        )

        tasks = [self._embed_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks)

        flat: list[tuple[Chunk, list[float]]] = []
        for pairs in results:
            flat.extend(pairs)
        return flat

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query string for retrieval."""
        vector = await self._embed_text(query)
        return vector

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _embed_batch(self, batch: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
        async with self._semaphore:
            tasks = [self._embed_text(chunk.text) for chunk in batch]
            vectors = await asyncio.gather(*tasks)
            return list(zip(batch, vectors))  # noqa: B905

    async def _embed_text(self, text: str) -> list[float]:
        """Wrap synchronous Bedrock call in executor to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._invoke_sync, text)
        except Exception:
            if settings.app_env == "development":
                logger.warning("bedrock_unavailable_dev_fallback", text_len=len(text))
                return self._deterministic_vector(text)
            raise

    @staticmethod
    def _deterministic_vector(text: str) -> list[float]:
        """Hash-based deterministic pseudo-embedding for local dev (no Bedrock)."""
        import hashlib
        import random as _random

        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
        rng = _random.Random(seed)
        floats = [rng.gauss(0.0, 1.0) for _ in range(1024)]
        norm = max(sum(x * x for x in floats) ** 0.5, 1e-9)
        return [x / norm for x in floats]

    def _invoke_sync(self, text: str) -> list[float]:
        import json

        payload: dict[str, Any] = {"inputText": text}
        response = self._client.invoke_model(
            modelId=self._model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload),
        )
        body = json.loads(response["body"].read())

        # Titan Embed v2 returns {"embedding": [...], "inputTextTokenCount": N}
        vector: list[float] = body["embedding"]
        return vector
