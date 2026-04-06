from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

_SQS_CONFIG = Config(
    region_name=settings.aws_region,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


@dataclass
class IngestionMessage:
    source_type: str  # "indiana_courts" | "s3_upload" | "odyssey"
    source_id: str  # unique identifier (case number, S3 key, etc.)
    download_url: str
    metadata: dict[str, Any]

    def to_body(self) -> str:
        return json.dumps(
            {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "download_url": self.download_url,
                "metadata": self.metadata,
            }
        )

    @classmethod
    def from_body(cls, body: str) -> IngestionMessage:
        data = json.loads(body)
        return cls(**data)


class SQSProducer:
    """Publishes ingestion messages to the SQS ingestion queue."""

    def __init__(self, queue_url: str = settings.sqs_ingestion_queue_url) -> None:
        self._queue_url = queue_url
        self._client = boto3.client("sqs", config=_SQS_CONFIG)

    async def publish(self, message: IngestionMessage) -> str:
        """Send a single message; returns the SQS MessageId."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=message.to_body(),
                MessageAttributes={
                    "SourceType": {
                        "DataType": "String",
                        "StringValue": message.source_type,
                    }
                },
            ),
        )
        msg_id: str = response["MessageId"]
        logger.info("sqs_published", message_id=msg_id, source_id=message.source_id)
        return msg_id

    async def publish_batch(self, messages: list[IngestionMessage]) -> int:
        """
        Send up to 10 messages per SQS batch call (AWS limit).
        Returns the number of successfully sent messages.
        """
        sent = 0
        for i in range(0, len(messages), 10):
            batch = messages[i : i + 10]
            entries = [
                {
                    "Id": str(j),
                    "MessageBody": msg.to_body(),
                }
                for j, msg in enumerate(batch)
            ]
            loop = asyncio.get_event_loop()
            batch_entries = entries

            def _send_batch(be: list[dict[str, Any]] = batch_entries) -> Any:
                return self._client.send_message_batch(QueueUrl=self._queue_url, Entries=be)

            response = await loop.run_in_executor(
                None,
                _send_batch,
            )
            failed = response.get("Failed", [])
            if failed:
                logger.error("sqs_batch_failures", count=len(failed), details=failed)
            sent += len(response.get("Successful", []))
        return sent


class SQSConsumer:
    """
    Long-poll SQS consumer for ingestion workers.

    Usage:
        async for message, receipt_handle in consumer.receive():
            await process(message)
            await consumer.delete(receipt_handle)
    """

    def __init__(
        self,
        queue_url: str = settings.sqs_ingestion_queue_url,
        max_messages: int = 10,
        visibility_timeout: int = 300,
        wait_seconds: int = 20,
    ) -> None:
        self._queue_url = queue_url
        self._max_messages = min(max_messages, 10)
        self._visibility_timeout = visibility_timeout
        self._wait_seconds = wait_seconds
        self._client = boto3.client("sqs", config=_SQS_CONFIG)

    async def receive(self) -> AsyncGenerator[tuple[IngestionMessage, str], None]:
        """Async generator yielding (IngestionMessage, receipt_handle) pairs."""
        loop = asyncio.get_event_loop()
        while True:
            response = await loop.run_in_executor(
                None,
                lambda: self._client.receive_message(
                    QueueUrl=self._queue_url,
                    MaxNumberOfMessages=self._max_messages,
                    VisibilityTimeout=self._visibility_timeout,
                    WaitTimeSeconds=self._wait_seconds,
                ),
            )
            sqs_messages = response.get("Messages", [])
            if not sqs_messages:
                await asyncio.sleep(1)
                continue

            for raw in sqs_messages:  # pragma: no branch
                try:
                    msg = IngestionMessage.from_body(raw["Body"])
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.error(
                        "sqs_parse_error", receipt=raw.get("ReceiptHandle"), error=str(exc)
                    )
                    await self.delete(raw["ReceiptHandle"])
                    continue
                yield msg, raw["ReceiptHandle"]

    async def delete(self, receipt_handle: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_message(
                QueueUrl=self._queue_url, ReceiptHandle=receipt_handle
            ),
        )
