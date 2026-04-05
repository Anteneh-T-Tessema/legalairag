"""Unit tests for retrieval.reranker — CrossEncoderReranker."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from retrieval.hybrid_search import SearchResult
from retrieval.reranker import CrossEncoderReranker


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _sr(source_id: str, content: str, score: float = 0.5) -> SearchResult:
    return SearchResult(
        chunk_id="c1",
        source_id=source_id,
        content=content,
        section="",
        citations=[],
        metadata={},
        score=score,
    )


class TestCrossEncoderReranker:
    def test_empty_results_returns_empty(self) -> None:
        reranker = CrossEncoderReranker()
        assert _run(reranker.rerank("query", [])) == []

    @patch("retrieval.reranker.CrossEncoderReranker._load_model")
    def test_rerank_sorts_by_score(self, mock_load: MagicMock) -> None:
        import numpy as np

        mock_model = MagicMock()
        # Scores: doc-b > doc-a > doc-c
        mock_model.predict.return_value = np.array([0.3, 0.9, 0.1])
        mock_load.return_value = mock_model

        results = [
            _sr("doc-a", "content a"),
            _sr("doc-b", "content b"),
            _sr("doc-c", "content c"),
        ]
        ranked = _run(CrossEncoderReranker().rerank("test query", results, top_k=2))

        assert len(ranked) == 2
        assert ranked[0].source_id == "doc-b"
        assert ranked[1].source_id == "doc-a"

    @patch("retrieval.reranker.CrossEncoderReranker._load_model")
    def test_rerank_respects_top_k(self, mock_load: MagicMock) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.5, 0.8, 0.2, 0.9])
        mock_load.return_value = mock_model

        results = [_sr(f"doc-{i}", f"content {i}") for i in range(4)]
        ranked = _run(CrossEncoderReranker().rerank("q", results, top_k=1))
        assert len(ranked) == 1

    @patch("retrieval.reranker.CrossEncoderReranker._load_model")
    def test_rerank_updates_scores(self, mock_load: MagicMock) -> None:
        import numpy as np

        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0.77])
        mock_load.return_value = mock_model

        results = [_sr("doc-1", "some content", score=0.1)]
        ranked = _run(CrossEncoderReranker().rerank("q", results, top_k=5))
        assert ranked[0].score == 0.77

    def test_lazy_model_init(self) -> None:
        reranker = CrossEncoderReranker()
        assert reranker._model is None
