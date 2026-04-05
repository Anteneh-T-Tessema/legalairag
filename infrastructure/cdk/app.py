#!/usr/bin/env python3
from aws_cdk import App
from stacks.api_stack import ApiStack
from stacks.cdn_stack import CdnStack
from stacks.ingestion_stack import IngestionStack
from stacks.observability_stack import ObservabilityStack
from stacks.retrieval_stack import RetrievalStack

app = App()

env_name = app.node.try_get_context("env") or "dev"

ingestion = IngestionStack(app, f"IndyLeg-Ingestion-{env_name}", env_name=env_name)
retrieval = RetrievalStack(app, f"IndyLeg-Retrieval-{env_name}", env_name=env_name)
api = ApiStack(
    app,
    f"IndyLeg-Api-{env_name}",
    env_name=env_name,
    ingestion_queue=ingestion.ingestion_queue,
)

ObservabilityStack(
    app,
    f"IndyLeg-Observability-{env_name}",
    env_name=env_name,
    api_service=api.service.service,
    api_service_cluster=api.service.cluster,
    alb_full_name=api.service.load_balancer.load_balancer_full_name,
    target_group_full_name=api.service.target_group.target_group_full_name,
    dlq=ingestion.dlq,
    ingestion_queue=ingestion.ingestion_queue,
)

CdnStack(
    app,
    f"IndyLeg-Cdn-{env_name}",
    env_name=env_name,
    alb=api.service.load_balancer,
)

app.synth()
