"""Unit tests for ingestion.pipeline.embedder — BedrockEmbedder."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

from ingestion.pipeline.chunker import Chunk


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_chunk(text: str = "sample text", chunk_id: str = "c1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id="src-1",
        text=text,
        section_header="§1",
        section_index=0,
        char_start=0,
        char_end=len(text),
        citations=[],
        metadata={},
    )


def _mock_invoke_response(embedding: list[float] | None = None):
    if embedding is None:
        embedding = [0.1] * 1024
    body_bytes = json.dumps({"embedding": embedding, "inputTextTokenCount": 5}).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    return {"body": mock_body}


class TestBedrockEmbedder:
    def _make_embedder(self, invoke_response=None):
        with patch("ingestion.pipeline.embedder.boto3.client") as mock_boto:
            mock_bedrock = MagicMock()
            mock_boto.return_value = mock_bedrock

            if invoke_response is None:
                invoke_response = _mock_invoke_response()
            mock_bedrock.invoke_model.return_value = invoke_response

            from ingestion.pipeline.embedder import BedrockEmbedder

            embedder = BedrockEmbedder.__new__(BedrockEmbedder)
            embedder._model_id = "amazon.titan-embed-text-v2:0"
            embedder._batch_size = 2
            embedder._semaphore = asyncio.Semaphore(2)
            embedder._client = mock_bedrock
            return embedder, mock_bedrock

    def test_embed_query_returns_vector(self):
        embedder, _ = self._make_embedder()
        vector = _run(embedder.embed_query("What is self defense?"))
        assert isinstance(vector, list)
        assert len(vector) == 1024

    def test_embed_query_calls_invoke_model(self):
        embedder, mock_bedrock = self._make_embedder()
        _run(embedder.embed_query("test query"))
        mock_bedrock.invoke_model.assert_called_once()
        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        body = json.loads(call_kwargs["body"])
        assert body["inputText"] == "test query"

    def test_embed_chunks_returns_pairs(self):
        embedder, _ = self._make_embedder()
        chunks = [_make_chunk("text1", "c1"), _make_chunk("text2", "c2")]
        pairs = _run(embedder.embed_chunks(chunks))
        assert len(pairs) == 2
        for chunk, vector in pairs:
            assert isinstance(chunk, Chunk)
            assert isinstance(vector, list)
            assert len(vector) == 1024

    def test_embed_chunks_batches_correctly(self):
        embedder, mock_bedrock = self._make_embedder()
        # batch_size=2, so 3 chunks should produce 2 batches
        chunks = [_make_chunk(f"t{i}", f"c{i}") for i in range(3)]
        pairs = _run(embedder.embed_chunks(chunks))
        assert len(pairs) == 3
        # invoke_model should be called 3 times (once per chunk)
        assert mock_bedrock.invoke_model.call_count == 3

    def test_embed_chunks_empty_list(self):
        embedder, _ = self._make_embedder()
        pairs = _run(embedder.embed_chunks([]))
        assert pairs == []

    def test_invoke_sync_parses_response(self):
        embedder, _ = self._make_embedder()
        vector = embedder._invoke_sync("hello")
        assert vector == [0.1] * 1024
