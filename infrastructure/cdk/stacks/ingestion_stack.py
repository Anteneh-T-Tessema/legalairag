from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class IngestionStack(cdk.Stack):
    """
    SQS-driven document ingestion pipeline.

    Architecture:
      S3 (raw)  →  SQS queue  →  ECS Fargate worker  →  S3 (processed)
                       ↓
                      DLQ (failed messages after 3 attempts)
    """

    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs: object) -> None:
        super().__init__(scope, id, **kwargs)

        # ── S3 buckets ────────────────────────────────────────────────────────
        self.raw_bucket = s3.Bucket(
            self,
            "RawDocuments",
            bucket_name=f"indyleg-raw-{env_name}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.processed_bucket = s3.Bucket(
            self,
            "ProcessedChunks",
            bucket_name=f"indyleg-processed-{env_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ── SQS queues ────────────────────────────────────────────────────────
        self.dlq = sqs.Queue(
            self,
            "IngestionDLQ",
            queue_name=f"indyleg-dlq-{env_name}",
            retention_period=Duration.days(14),
        )

        self.ingestion_queue = sqs.Queue(
            self,
            "IngestionQueue",
            queue_name=f"indyleg-ingestion-{env_name}",
            visibility_timeout=Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq,
            ),
        )

        self.embedding_queue = sqs.Queue(
            self,
            "EmbeddingQueue",
            queue_name=f"indyleg-embedding-{env_name}",
            visibility_timeout=Duration.minutes(10),
        )

        # ── ECS Worker ────────────────────────────────────────────────────────
        cluster = ecs.Cluster(self, "IngestionCluster")

        worker_task = ecs.FargateTaskDefinition(
            self,
            "WorkerTask",
            cpu=2048,
            memory_limit_mib=4096,
        )

        worker_task.add_container(
            "WorkerContainer",
            image=ecs.ContainerImage.from_asset("../../", file="infrastructure/docker/Dockerfile.worker"),
            environment={
                "SQS_INGESTION_QUEUE_URL": self.ingestion_queue.queue_url,
                "S3_BUCKET_RAW": self.raw_bucket.bucket_name,
                "S3_BUCKET_PROCESSED": self.processed_bucket.bucket_name,
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="indyleg-worker"),
        )

        # Grant permissions
        self.ingestion_queue.grant_consume_messages(worker_task.task_role)
        self.raw_bucket.grant_read(worker_task.task_role)
        self.processed_bucket.grant_write(worker_task.task_role)

        # Bedrock access
        worker_task.task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess")
        )
