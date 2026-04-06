"""Tests for the lazy-loading __getattr__ in ingestion/__init__.py."""

from __future__ import annotations

import pytest


def test_getattr_chunk():
    import ingestion

    obj = ingestion.Chunk
    from ingestion.pipeline.chunker import Chunk

    assert obj is Chunk


def test_getattr_legal_chunker():
    import ingestion

    obj = ingestion.LegalChunker
    from ingestion.pipeline.chunker import LegalChunker

    assert obj is LegalChunker


def test_getattr_bedrock_embedder():
    import ingestion

    obj = ingestion.BedrockEmbedder
    from ingestion.pipeline.embedder import BedrockEmbedder

    assert obj is BedrockEmbedder


def test_getattr_ingestion_worker():
    import ingestion

    obj = ingestion.IngestionWorker
    from ingestion.pipeline.worker import IngestionWorker

    assert obj is IngestionWorker


def test_getattr_ingestion_message():
    import ingestion

    obj = ingestion.IngestionMessage
    from ingestion.queue.sqs import IngestionMessage

    assert obj is IngestionMessage


def test_getattr_sqs_consumer():
    import ingestion

    obj = ingestion.SQSConsumer
    from ingestion.queue.sqs import SQSConsumer

    assert obj is SQSConsumer


def test_getattr_sqs_producer():
    import ingestion

    obj = ingestion.SQSProducer
    from ingestion.queue.sqs import SQSProducer

    assert obj is SQSProducer


def test_getattr_unknown_name_raises_attribute_error():
    import ingestion

    with pytest.raises(AttributeError, match="module 'ingestion' has no attribute 'NonExistent'"):
        _ = ingestion.NonExistent
