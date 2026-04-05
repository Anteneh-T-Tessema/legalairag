#!/bin/bash
# LocalStack initialization script — creates S3 buckets and SQS queues for local dev.
# Mounted into /etc/localstack/init/ready.d/ by docker-compose.

set -euo pipefail

echo "=== Initializing LocalStack resources ==="

# S3 Buckets
awslocal s3 mb s3://indyleg-raw-documents
awslocal s3 mb s3://indyleg-processed-chunks

# SQS Dead Letter Queue
awslocal sqs create-queue --queue-name indyleg-dlq

DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://sqs.us-east-1.localhost.localstack.cloud:4566/000000000000/indyleg-dlq \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' --output text)

# SQS Ingestion Queue (with DLQ)
awslocal sqs create-queue \
  --queue-name indyleg-ingestion \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

# SQS Embedding Queue
awslocal sqs create-queue \
  --queue-name indyleg-embedding \
  --attributes "{\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

echo "=== LocalStack resources created ==="
echo "S3 Buckets:"
awslocal s3 ls
echo "SQS Queues:"
awslocal sqs list-queues
