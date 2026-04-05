"""Integration tests for SQS queue operations using LocalStack.

Requires: docker-compose services (localstack) running.
Run: pytest tests/integration/test_sqs.py -v --timeout=60
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("LOCALSTACK_AVAILABLE", ""),
    reason="LOCALSTACK_AVAILABLE not set — start docker-compose localstack first",
)


@pytest.fixture(scope="module")
def sqs_client():
    import boto3

    return boto3.client(
        "sqs",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture
def queue_url(sqs_client):
    name = f"test-queue-{uuid.uuid4().hex[:8]}"
    resp = sqs_client.create_queue(QueueName=name)
    url = resp["QueueUrl"]
    yield url
    sqs_client.delete_queue(QueueUrl=url)


class TestSQSIntegration:
    """Tests SQS send/receive with LocalStack."""

    def test_send_and_receive_message(self, sqs_client, queue_url: str) -> None:
        body = {"source_type": "indiana_courts", "source_id": "case-001"}
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(body),
        )

        resp = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1
        assert json.loads(messages[0]["Body"]) == body

    def test_batch_send(self, sqs_client, queue_url: str) -> None:
        entries = [{"Id": str(i), "MessageBody": json.dumps({"doc": i})} for i in range(10)]
        resp = sqs_client.send_message_batch(QueueUrl=queue_url, Entries=entries)
        assert len(resp.get("Successful", [])) == 10

    def test_dlq_redrive(self, sqs_client) -> None:
        """Verify DLQ receives messages after max receives."""
        dlq_name = f"test-dlq-{uuid.uuid4().hex[:8]}"
        dlq_resp = sqs_client.create_queue(QueueName=dlq_name)
        dlq_url = dlq_resp["QueueUrl"]
        dlq_arn = sqs_client.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]

        queue_name = f"test-main-{uuid.uuid4().hex[:8]}"
        queue_resp = sqs_client.create_queue(
            QueueName=queue_name,
            Attributes={
                "RedrivePolicy": json.dumps(
                    {
                        "deadLetterTargetArn": dlq_arn,
                        "maxReceiveCount": "1",
                    }
                ),
            },
        )
        queue_url = queue_resp["QueueUrl"]

        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody="test-dlq-message",
        )

        # Receive and don't delete (simulates processing failure)
        sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            VisibilityTimeout=0,
        )

        # Cleanup
        sqs_client.delete_queue(QueueUrl=queue_url)
        sqs_client.delete_queue(QueueUrl=dlq_url)
