"""Integration tests for AWS Bedrock (embeddings and LLM).

Requires: AWS credentials with Bedrock access.
Run: pytest tests/integration/test_bedrock.py -v --timeout=120
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("AWS_ACCESS_KEY_ID"),
    reason="AWS credentials not set — configure AWS_ACCESS_KEY_ID/SECRET for Bedrock tests",
)


class TestBedrockEmbeddings:
    """Tests Bedrock Titan Embed v2 integration."""

    def test_single_embedding(self) -> None:
        """Generate embedding for a single text."""
        import boto3

        client = boto3.client("bedrock-runtime", region_name="us-east-1")
        import json

        body = json.dumps({"inputText": "Indiana eviction notice requirements"})
        response = client.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=body,
            contentType="application/json",
        )
        result = json.loads(response["body"].read())
        embedding = result["embedding"]

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        assert all(isinstance(v, float) for v in embedding)

    def test_batch_embeddings(self) -> None:
        """Generate embeddings for multiple texts."""
        from ingestion.pipeline.embedder import BedrockEmbedder
        import asyncio

        embedder = BedrockEmbedder()
        texts = [
            "Indiana Code § 35-42-1-1 defines murder",
            "Small claims court filing deadlines",
            "Marion County eviction procedures",
        ]
        vectors = asyncio.get_event_loop().run_until_complete(
            embedder.embed_batch(texts)
        )
        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)

    def test_query_embedding(self) -> None:
        """Embed a query for retrieval."""
        from ingestion.pipeline.embedder import BedrockEmbedder
        import asyncio

        embedder = BedrockEmbedder()
        vector = asyncio.get_event_loop().run_until_complete(
            embedder.embed_query("What are Indiana self-defense laws?")
        )
        assert len(vector) == 1024


class TestBedrockLLM:
    """Tests Bedrock Claude integration."""

    def test_converse_api(self) -> None:
        """Basic Claude completion via Converse API."""
        from generation.bedrock_client import BedrockLLMClient

        client = BedrockLLMClient()
        response = client.complete(
            system="You are a legal research assistant. Be concise.",
            messages=[
                {"role": "user", "content": "What is IC 35-42-1-1 about? Answer in one sentence."}
            ],
            temperature=0.0,
        )
        assert isinstance(response, str)
        assert len(response) > 10

    def test_streaming(self) -> None:
        """Streaming response from Claude."""
        from generation.bedrock_client import BedrockLLMClient

        client = BedrockLLMClient()
        chunks = list(client.stream(
            system="Be brief.",
            messages=[
                {"role": "user", "content": "Name one Indiana county."}
            ],
        ))
        assert len(chunks) > 0
        full_text = "".join(chunks)
        assert len(full_text) > 0

    def test_citation_grounded_generation(self) -> None:
        """End-to-end: generate a citation-grounded answer."""
        from generation.generator import LegalGenerator
        from retrieval.hybrid_search import SearchResult
        import asyncio

        generator = LegalGenerator()
        mock_context = [
            SearchResult(
                chunk_id="c1",
                source_id="IC-35-42-1-1",
                section="definition",
                content="Under Indiana Code § 35-42-1-1, a person who knowingly or intentionally kills another human being commits murder, a Level 1 felony.",
                citations=["IC 35-42-1-1"],
                score=0.95,
            ),
        ]
        result = asyncio.get_event_loop().run_until_complete(
            generator.generate(
                query="What is murder under Indiana law?",
                context_chunks=mock_context,
                jurisdiction="Indiana",
            )
        )
        assert result.answer
        assert result.model_id
