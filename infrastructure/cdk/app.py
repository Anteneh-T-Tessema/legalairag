#!/usr/bin/env python3
from aws_cdk import App
from stacks.api_stack import ApiStack
from stacks.ingestion_stack import IngestionStack
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

app.synth()
