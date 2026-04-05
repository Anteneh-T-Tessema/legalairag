from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    api_secret_key: SecretStr = Field(
        default="dev-secret-change-in-production",
        description="HMAC signing key for API",
    )
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── AWS ──────────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"
    aws_account_id: str = ""

    # ── Bedrock ──────────────────────────────────────────────────────────────
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    bedrock_llm_model: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_max_tokens: int = 4096

    # ── Storage ───────────────────────────────────────────────────────────────
    s3_bucket_raw: str = "indyleg-raw-documents"
    s3_bucket_processed: str = "indyleg-processed-chunks"

    # ── Queues ────────────────────────────────────────────────────────────────
    sqs_ingestion_queue_url: str = ""
    sqs_embedding_queue_url: str = ""
    sqs_dlq_url: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://indyleg:changeme@localhost:5432/indyleg"
    vector_dimension: int = 1024

    # ── OpenSearch ────────────────────────────────────────────────────────────
    opensearch_host: str = "https://localhost:9200"
    opensearch_index: str = "indyleg-legal-docs"

    # ── Indiana Courts ────────────────────────────────────────────────────────
    indiana_courts_api_base: str = "https://public.courts.in.gov/api"
    indiana_courts_api_key: str = ""

    # ── Public Legal Sources ─────────────────────────────────────────────────
    # CourtListener (Free Law Project) — https://www.courtlistener.com/api/
    courtlistener_api_token: str = ""  # Register free at courtlistener.com
    courtlistener_api_base: str = "https://www.courtlistener.com/api/rest/v4"
    courtlistener_max_pages: int = 5  # Max pagination depth per court
    # law.resource.org Federal Reporter bulk downloads
    law_resource_base: str = "https://law.resource.org/pub/us/case/reporter"
    law_resource_indiana_filter: bool = True  # Filter 7th Cir opinions for Indiana
    # Indiana General Assembly — statutes
    indiana_iga_api_base: str = "https://iga.in.gov/api/20231116/mobile-sdk"

    # ── Evaluation ────────────────────────────────────────────────────────────
    eval_dataset_path: str = "tests/data/eval_queries.json"
    eval_k_values: list[int] = [1, 5, 10]

    # ── Fraud Detection ───────────────────────────────────────────────────────
    fraud_detection_top_k: int = 50  # Wide net for pattern analysis
    fraud_burst_filing_threshold: int = 5  # Cases/party/30 days to flag

    # ── Authority Ranking ─────────────────────────────────────────────────────
    authority_alpha_default: float = 0.30  # Authority blend weight (0=retrieval, 1=authority)

    # ── Performance ───────────────────────────────────────────────────────────
    embedding_batch_size: int = 128
    ingestion_worker_concurrency: int = 4
    rerank_top_k: int = 20
    retrieval_top_k: int = 5


settings = Settings()
