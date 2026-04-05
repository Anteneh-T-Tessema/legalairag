from __future__ import annotations

import asyncio
from typing import Any

from config.logging import get_logger
from config.settings import settings
from retrieval.hybrid_search import SearchResult

logger = get_logger(__name__)


class CrossEncoderReranker:
    """
    Re-ranks hybrid search results using a cross-encoder model.

    Why cross-encoder:
    - Bi-encoder (used for embedding) is fast but encodes query and document
      independently → misses fine-grained interaction signals.
    - Cross-encoder reads (query, document) jointly → better legal relevance
      at the cost of higher latency (acceptable after pre-filtering to top-20).

    Default model: ms-marco-MiniLM-L-6-v2 (fast, good for IR tasks).
    For production, consider a legal-domain fine-tuned cross-encoder.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        batch_size: int = 32,
    ) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._model: Any = None  # lazy-loaded

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name, max_length=512)
            logger.info("cross_encoder_loaded", model=self._model_name)
        return self._model

    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = settings.retrieval_top_k,
    ) -> list[SearchResult]:
        """
        Score each (query, chunk) pair and return top_k by cross-encoder score.
        Batched to maintain latency targets.
        """
        if not results:
            return []

        model = await asyncio.get_event_loop().run_in_executor(None, self._load_model)

        pairs = [(query, r.content) for r in results]
        scores: list[float] = []

        for i in range(0, len(pairs), self._batch_size):
            batch = pairs[i : i + self._batch_size]
            batch_scores: list[float] = await asyncio.get_event_loop().run_in_executor(
                None, lambda b=batch: model.predict(b).tolist()  # type: ignore[misc]
            )
            scores.extend(batch_scores)

        ranked = sorted(
            zip(results, scores),  # noqa: B905
            key=lambda x: x[1],
            reverse=True,
        )

        top = ranked[:top_k]
        for result, score in top:
            result.score = float(score)

        logger.info(
            "reranked",
            input_count=len(results),
            output_count=len(top),
            top_score=top[0][1] if top else None,
        )
        return [r for r, _ in top]
