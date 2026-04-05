from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_opensearchservice as opensearch,
    RemovalPolicy,
)
from constructs import Construct


class RetrievalStack(cdk.Stack):
    """
    Retrieval infrastructure:
    - RDS Aurora PostgreSQL + pgvector for dense vector search
    - Amazon OpenSearch for BM25 keyword search
    Both sit inside a private VPC subnet.
    """

    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs: object) -> None:
        super().__init__(scope, id, **kwargs)

        self.vpc = ec2.Vpc(self, "IndyLegVpc", max_azs=2, nat_gateways=1)

        # ── Aurora PostgreSQL (pgvector) ──────────────────────────────────────
        self.db_cluster = rds.DatabaseCluster(
            self,
            "VectorDB",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_16_2
            ),
            writer=rds.ClusterInstance.provisioned("Writer", instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.R6G, ec2.InstanceSize.LARGE
            )),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            removal_policy=RemovalPolicy.SNAPSHOT,
            default_database_name="indyleg",
        )

        # ── OpenSearch (BM25) ─────────────────────────────────────────────────
        self.search_domain = opensearch.Domain(
            self,
            "SearchDomain",
            domain_name=f"indyleg-{env_name}",
            version=opensearch.EngineVersion.OPENSEARCH_2_13,
            capacity=opensearch.CapacityConfig(
                data_nodes=2,
                data_node_instance_type="r6g.large.search",
            ),
            ebs=opensearch.EbsOptions(
                enabled=True,
                volume_size=100,
            ),
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            removal_policy=RemovalPolicy.RETAIN,
            encryption_at_rest=opensearch.EncryptionAtRestOptions(enabled=True),
            node_to_node_encryption=True,
            enforce_https=True,
        )
