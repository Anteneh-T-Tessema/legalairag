"""Unit tests for ingestion.queue.sqs – IngestionMessage + SQSProducer."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ingestion.queue.sqs import IngestionMessage

# ── IngestionMessage ──────────────────────────────────────────────────────────


class TestIngestionMessage:
    def test_to_body_produces_valid_json(self):
        msg = IngestionMessage(
            source_type="indiana_courts",
            source_id="49D01-2403-CM-012345",
            download_url="https://courts.in.gov/case/12345.pdf",
            metadata={"county": "Marion"},
        )
        body = msg.to_body()
        data = json.loads(body)
        assert data["source_type"] == "indiana_courts"
        assert data["source_id"] == "49D01-2403-CM-012345"
        assert data["download_url"] == "https://courts.in.gov/case/12345.pdf"
        assert data["metadata"]["county"] == "Marion"

    def test_from_body_roundtrips(self):
        original = IngestionMessage(
            source_type="s3_upload",
            source_id="uploads/brief.pdf",
            download_url="s3://bucket/uploads/brief.pdf",
            metadata={"uploaded_by": "user-1"},
        )
        restored = IngestionMessage.from_body(original.to_body())
        assert restored.source_type == original.source_type
        assert restored.source_id == original.source_id
        assert restored.download_url == original.download_url
        assert restored.metadata == original.metadata

    def test_from_body_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            IngestionMessage.from_body("not json")

    def test_from_body_raises_on_missing_fields(self):
        with pytest.raises((KeyError, TypeError)):
            IngestionMessage.from_body(json.dumps({"source_type": "x"}))

    def test_metadata_can_be_empty(self):
        msg = IngestionMessage(
            source_type="odyssey",
            source_id="case-99",
            download_url="https://example.com/doc",
            metadata={},
        )
        data = json.loads(msg.to_body())
        assert data["metadata"] == {}


# ── SQSProducer ───────────────────────────────────────────────────────────────


class TestSQSProducer:
    @pytest.mark.asyncio
    async def test_publish_returns_message_id(self):
        with patch("ingestion.queue.sqs.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.send_message.return_value = {"MessageId": "msg-abc-123"}
            mock_boto.client.return_value = mock_client

            from ingestion.queue.sqs import SQSProducer

            producer = SQSProducer(queue_url="https://sqs.us-east-1.amazonaws.com/123/queue")
            producer._client = mock_client

            msg = IngestionMessage(
                source_type="indiana_courts",
                source_id="case-1",
                download_url="https://example.com/doc.pdf",
                metadata={},
            )
            result = await producer.publish(msg)
            assert result == "msg-abc-123"
            mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_sends_correct_body(self):
        with patch("ingestion.queue.sqs.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.send_message.return_value = {"MessageId": "msg-1"}
            mock_boto.client.return_value = mock_client

            from ingestion.queue.sqs import SQSProducer

            producer = SQSProducer(queue_url="https://sqs.example.com/queue")
            producer._client = mock_client

            msg = IngestionMessage(
                source_type="s3_upload",
                source_id="key-1",
                download_url="s3://bucket/key",
                metadata={"size": 1024},
            )
            await producer.publish(msg)

            call_kwargs = mock_client.send_message.call_args
            kw = call_kwargs[1]
            body = json.loads(kw["MessageBody"] if kw else call_kwargs[0][0])
            assert body["source_type"] == "s3_upload"

    @pytest.mark.asyncio
    async def test_publish_batch_single_batch(self):
        with patch("ingestion.queue.sqs.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.send_message_batch.return_value = {
                "Successful": [{"Id": "0"}, {"Id": "1"}, {"Id": "2"}],
                "Failed": [],
            }
            mock_boto.client.return_value = mock_client

            from ingestion.queue.sqs import SQSProducer

            producer = SQSProducer(queue_url="https://sqs.example.com/queue")
            producer._client = mock_client

            messages = [
                IngestionMessage(
                    source_type="indiana_courts",
                    source_id=f"case-{i}",
                    download_url=f"https://example.com/{i}.pdf",
                    metadata={},
                )
                for i in range(3)
            ]
            sent = await producer.publish_batch(messages)
            assert sent == 3
            mock_client.send_message_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_batch_splits_at_10(self):
        with patch("ingestion.queue.sqs.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.send_message_batch.return_value = {
                "Successful": [{"Id": str(i)} for i in range(10)],
                "Failed": [],
            }
            mock_boto.client.return_value = mock_client

            from ingestion.queue.sqs import SQSProducer

            producer = SQSProducer(queue_url="https://sqs.example.com/queue")
            producer._client = mock_client

            messages = [
                IngestionMessage(
                    source_type="indiana_courts",
                    source_id=f"case-{i}",
                    download_url=f"https://example.com/{i}.pdf",
                    metadata={},
                )
                for i in range(15)
            ]
            sent = await producer.publish_batch(messages)
            # 2 batches: 10 + 5
            assert mock_client.send_message_batch.call_count == 2
            assert sent == 20  # mock returns 10 each call

    @pytest.mark.asyncio
    async def test_publish_batch_handles_failures(self):
        with patch("ingestion.queue.sqs.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_client.send_message_batch.return_value = {
                "Successful": [{"Id": "0"}],
                "Failed": [{"Id": "1", "Code": "InternalError", "Message": "err"}],
            }
            mock_boto.client.return_value = mock_client

            from ingestion.queue.sqs import SQSProducer

            producer = SQSProducer(queue_url="https://sqs.example.com/queue")
            producer._client = mock_client

            messages = [
                IngestionMessage(
                    source_type="test",
                    source_id=f"case-{i}",
                    download_url=f"https://example.com/{i}",
                    metadata={},
                )
                for i in range(2)
            ]
            sent = await producer.publish_batch(messages)
            assert sent == 1  # Only 1 succeeded


# ── SQSConsumer ───────────────────────────────────────────────────────────────


class TestSQSConsumer:
    def test_consumer_respects_max_messages(self):
        with patch("ingestion.queue.sqs.boto3"):
            from ingestion.queue.sqs import SQSConsumer

            consumer = SQSConsumer(
                queue_url="https://sqs.example.com/queue",
                max_messages=20,
            )
            assert consumer._max_messages == 10  # clamped to AWS limit

    def test_consumer_default_visibility_timeout(self):
        with patch("ingestion.queue.sqs.boto3"):
            from ingestion.queue.sqs import SQSConsumer

            consumer = SQSConsumer(queue_url="https://sqs.example.com/queue")
            assert consumer._visibility_timeout == 300
