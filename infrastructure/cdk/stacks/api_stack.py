from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_ecs_patterns as ecs_patterns,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from constructs import Construct


class ApiStack(cdk.Stack):
    """
    FastAPI application running on ECS Fargate behind an ALB.

    Routes:
      ALB :443  →  ECS Fargate (api container, port 8000)

    The API needs:
      - SQS send (document ingestion)
      - Bedrock invoke (embedding + LLM)
      - RDS / OpenSearch read (retrieval) — via security group ingress
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        env_name: str,
        ingestion_queue: sqs.IQueue,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Import VPC from retrieval stack (shared)
        vpc = ec2.Vpc.from_lookup(self, "Vpc", vpc_name="IndyLeg-Retrieval-*/IndyLegVpc")

        cluster = ecs.Cluster(self, "ApiCluster", vpc=vpc)

        # ── Fargate service behind ALB ────────────────────────────────────────
        self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "ApiService",
            cluster=cluster,
            cpu=1024,
            memory_limit_mib=2048,
            desired_count=2,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "../../",
                    file="infrastructure/docker/Dockerfile.api",
                ),
                container_port=8000,
                environment={
                    "APP_ENV": env_name,
                    "SQS_INGESTION_QUEUE_URL": ingestion_queue.queue_url,
                },
            ),
            public_load_balancer=True,
            health_check_grace_period=Duration.seconds(60),
        )

        # Health check
        self.service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
        )

        # Auto-scaling: 2–6 tasks based on CPU
        scaling = self.service.service.auto_scale_task_count(
            min_capacity=2,
            max_capacity=6,
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(120),
            scale_out_cooldown=Duration.seconds(60),
        )

        # ── Permissions ───────────────────────────────────────────────────────
        task_role = self.service.task_definition.task_role

        # SQS: send messages to ingestion queue
        ingestion_queue.grant_send_messages(task_role)

        # Bedrock: invoke models
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self,
            "ApiUrl",
            value=self.service.load_balancer.load_balancer_dns_name,
            description="ALB DNS name for the IndyLeg API",
        )
