"""Document ingestion pipeline – SQS queue, chunking, embedding."""

__all__ = [
    "BedrockEmbedder",
    "Chunk",
    "IngestionMessage",
    "IngestionWorker",
    "LegalChunker",
    "SQSConsumer",
    "SQSProducer",
]


def __getattr__(name: str):  # noqa: C901
    if name in ("Chunk", "LegalChunker"):
        from ingestion.pipeline.chunker import Chunk, LegalChunker
        return {"Chunk": Chunk, "LegalChunker": LegalChunker}[name]
    if name == "BedrockEmbedder":
        from ingestion.pipeline.embedder import BedrockEmbedder
        return BedrockEmbedder
    if name == "IngestionWorker":
        from ingestion.pipeline.worker import IngestionWorker
        return IngestionWorker
    if name in ("IngestionMessage", "SQSConsumer", "SQSProducer"):
        from ingestion.queue.sqs import IngestionMessage, SQSConsumer, SQSProducer

        _sqs_exports = {
            "IngestionMessage": IngestionMessage,
            "SQSConsumer": SQSConsumer,
            "SQSProducer": SQSProducer,
        }
        return _sqs_exports[name]
    raise AttributeError(f"module 'ingestion' has no attribute {name!r}")
