"""Document ingestion pipeline – SQS queue, chunking, embedding."""

from ingestion.pipeline.chunker import Chunk, LegalChunker
from ingestion.pipeline.embedder import BedrockEmbedder
from ingestion.pipeline.worker import IngestionWorker
from ingestion.queue.sqs import IngestionMessage, SQSConsumer, SQSProducer

__all__ = [
    "BedrockEmbedder",
    "Chunk",
    "IngestionMessage",
    "IngestionWorker",
    "LegalChunker",
    "SQSConsumer",
    "SQSProducer",
]
