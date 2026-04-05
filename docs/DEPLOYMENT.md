# Deployment Guide

**Project**: IndyLeg — Indiana Legal AI RAG Platform
**Version**: 0.2.0 | **Date**: April 2026

---

## Table of Contents

- [1. Deployment Options](#1-deployment-options)
- [2. Local Development (Docker Compose)](#2-local-development-docker-compose)
- [3. Local Development (Bare Metal)](#3-local-development-bare-metal)
- [4. AWS Deployment (CDK)](#4-aws-deployment-cdk)
- [5. CDK Stacks](#5-cdk-stacks)
- [6. Environment Variables](#6-environment-variables)
- [7. CI/CD Pipeline](#7-cicd-pipeline)
- [8. Post-Deployment Verification](#8-post-deployment-verification)
- [9. Rollback Procedures](#9-rollback-procedures)

---

## 1. Deployment Options

| Method | Use Case | Prerequisites |
|---|---|---|
| **Docker Compose** | Local development, demo | Docker, Docker Compose |
| **Bare Metal** | Debugging, IDE integration | Python 3.11+, Node.js 18+, PostgreSQL 16, OpenSearch |
| **AWS CDK** | Staging, production | AWS CLI, CDK CLI, Node.js, Python 3.11+ |

---

## 2. Local Development (Docker Compose)

### Quick Start

```bash
# Clone and start everything
git clone https://github.com/Anteneh-T-Tessema/legalairag.git
cd legalairag
make up
```

This starts 6 services:

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | Vector store + relational data |
| `opensearch` | `opensearchproject/opensearch:2.14.0` | 9200 | BM25 keyword search |
| `localstack` | `localstack/localstack:3.5` | 4566 | S3 + SQS emulation |
| `api` | `Dockerfile.api` | 8000 | FastAPI REST API |
| `worker` | `Dockerfile.worker` | — | Ingestion worker |
| `ui` | `ui/Dockerfile` | 3000 | React frontend |

### Service Health Checks

```bash
# Check all services are healthy
docker compose ps

# Verify API
curl http://localhost:8000/health

# Verify OpenSearch
curl http://localhost:9200/_cluster/health

# Verify PostgreSQL
docker compose exec postgres pg_isready -U indyleg
```

### Stopping

```bash
make down                    # Stop services, keep volumes
docker compose down -v       # Stop services AND delete volumes (data loss)
```

### Docker Compose Architecture

```text
┌──────────────────────────────────────────────────────────┐
│                    Docker Network                         │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐  │
│  │ postgres │  │ opensearch│  │ localstack           │  │
│  │ :5432    │  │ :9200     │  │ :4566 (S3+SQS)      │  │
│  └────▲─────┘  └────▲──────┘  └──────────▲───────────┘  │
│       │              │                    │              │
│  ┌────┴──────────────┴────────────────────┴───────────┐  │
│  │                    api :8000                        │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────┴──────────────┴────────────────────┴───────────┐  │
│  │                   worker                            │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │               ui :3000 → api:8000                  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Environment File

Create `.env` in the project root for local overrides:

```bash
# .env (local development)
APP_ENV=development
JWT_SECRET_KEY=dev-secret-key-change-in-production
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
```

The Docker Compose file provides service-specific defaults (database URLs, AWS endpoints).

---

## 3. Local Development (Bare Metal)

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- PostgreSQL 16 with pgvector extension
- OpenSearch 2.14 (or Docker for just infrastructure)

### Setup

```bash
# 1. Start infrastructure only
make dev

# 2. Install Python dependencies
pip install -e ".[dev]"

# 3. Run API server with hot reload
make api

# 4. Run ingestion worker (separate terminal)
make worker

# 5. Run UI dev server (separate terminal)
make ui
```

### Running Tests

```bash
make test             # All tests (187 total)
make test-unit        # Unit tests only (167 Python + 20 UI)
make test-integration # Integration tests (requires running services)
make lint             # ruff check + pyright
make format           # Auto-format code
```

---

## 4. AWS Deployment (CDK)

### Prerequisites

```bash
# 1. AWS CLI configured
aws configure

# 2. Node.js + CDK CLI
npm install -g aws-cdk

# 3. Python 3.11+
python --version

# 4. CDK dependencies
pip install aws-cdk-lib constructs
```

### Deploy

```bash
# Deploy to dev environment
./infrastructure/deploy.sh dev

# Deploy to staging
./infrastructure/deploy.sh staging

# Deploy to production
./infrastructure/deploy.sh prod
```

### What `deploy.sh` Does

```text
1. Build UI (npm ci && npm run build)
2. Install CDK Python dependencies
3. CDK bootstrap (first time — creates staging S3 bucket)
4. CDK synth (validates CloudFormation templates)
5. CDK deploy all stacks (requires approval for IAM changes)
6. Output API URL to outputs-{env}.json
```

### Manual CDK Commands

```bash
cd infrastructure/cdk

# Preview changes
cdk diff --context env=dev

# Synthesize templates only
cdk synth --context env=dev

# Deploy specific stack
cdk deploy IndyLeg-Retrieval-dev --context env=dev

# Destroy all stacks
cdk destroy --all --context env=dev
```

---

## 5. CDK Stacks

Three stacks deployed in dependency order:

```mermaid
graph TB
    RS[RetrievalStack] --> IS[IngestionStack]
    RS --> AS[ApiStack]
    IS --> AS
```

### Stack Details

| Stack | Resources | AWSServices |
|---|---|---|
| **RetrievalStack** | VPC, Aurora PostgreSQL (pgvector), OpenSearch domain, ElastiCache Redis | RDS, OpenSearch Service, ElastiCache, VPC |
| **IngestionStack** | S3 bucket, SQS queue + DLQ, ECS worker task definition | S3, SQS, ECS, Fargate |
| **ApiStack** | ECS Fargate service, ALB, target group, security groups | ECS, Fargate, ALB, ACM |

### Resource Naming

```text
IndyLeg-{Stack}-{env}

Examples:
IndyLeg-Retrieval-prod
IndyLeg-Ingestion-staging
IndyLeg-Api-dev
```

### AWS Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                        VPC (3 AZs)                           │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   Public Subnets                         │ │
│  │  ┌─────────────────────────────┐                        │ │
│  │  │      Application Load       │ ← HTTPS (ACM cert)    │ │
│  │  │         Balancer            │                        │ │
│  │  └─────────────┬───────────────┘                        │ │
│  └────────────────┼────────────────────────────────────────┘ │
│                   │                                          │
│  ┌────────────────┼────────────────────────────────────────┐ │
│  │                │      Private Subnets                    │ │
│  │  ┌─────────────▼───────────────┐                        │ │
│  │  │   ECS Fargate (API)         │                        │ │
│  │  │   2 tasks, 512 CPU, 1GB    │                        │ │
│  │  └──────┬──────────┬───────────┘                        │ │
│  │         │          │                                    │ │
│  │  ┌──────▼─────┐ ┌──▼──────────┐ ┌──────────────────┐   │ │
│  │  │ Aurora     │ │ OpenSearch  │ │ ElastiCache      │   │ │
│  │  │ PostgreSQL │ │ 2.14       │ │ Redis            │   │ │
│  │  │ (pgvector) │ │            │ │                  │   │ │
│  │  └────────────┘ └────────────┘ └──────────────────┘   │ │
│  │                                                        │ │
│  │  ┌──────────────┐  ┌──────────┐                        │ │
│  │  │ ECS Worker   │  │ SQS      │                        │ │
│  │  │ (Ingestion)  │◄─┤ Queue    │                        │ │
│  │  └──────────────┘  │ + DLQ    │                        │ │
│  │                     └──────────┘                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────┐  ┌──────────────────┐                   │
│  │ S3 Bucket       │  │ SSM Param Store  │                   │
│  │ (Documents)     │  │ + Secrets Mgr    │                   │
│  └─────────────────┘  └──────────────────┘                   │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 AWS Bedrock                              │ │
│  │  Claude 3.5 Sonnet (generation)                         │ │
│  │  Titan Embed Text v2 (embeddings, 1024-dim)             │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Environment Variables

### Required (All Environments)

| Variable | Description | Example |
|---|---|---|
| `APP_ENV` | Environment name | `development`, `staging`, `production` |
| `JWT_SECRET_KEY` | JWT signing key (use secrets manager in prod) | `(generated)` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://user:pass@host:5432/db` |
| `OPENSEARCH_HOST` | OpenSearch endpoint | `https://search.us-east-1.es.amazonaws.com` |

### Optional

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `indyleg` | Application name |
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-sonnet...` | LLM model for generation |
| `BEDROCK_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Embedding model |
| `SQS_INGESTION_QUEUE_URL` | — | SQS queue for ingestion |
| `S3_DOCUMENT_BUCKET` | `indyleg-documents` | S3 bucket for raw documents |
| `RATE_LIMIT_RPM` | `60` | Rate limit requests per minute |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `VECTOR_DIMENSION` | `1024` | Embedding dimension |
| `SECRET_RESOLUTION_ORDER` | `ssm,secretsmanager` | Secrets cascade order |

---

## 7. CI/CD Pipeline

### GitHub Actions Workflow

```text
Push to main
    │
    ├─► Lint (ruff check + pyright)
    ├─► Unit Tests (pytest tests/unit/)
    ├─► UI Tests (vitest)
    │
    ▼ All pass
    │
    ├─► Build Docker images
    ├─► Push to ECR
    │
    ▼
    │
    ├─► Integration Tests (with test DB)
    │
    ▼ All pass
    │
    ├─► CDK Deploy to staging
    ├─► Smoke tests against staging
    │
    ▼ Manual approval
    │
    └─► CDK Deploy to production
```

### Build Commands

```bash
# Lint
ruff check .
ruff format --check .
pyright

# Test
pytest tests/unit/ -v --tb=short
cd ui && npx vitest run

# Docker Build
docker build -f infrastructure/docker/Dockerfile.api -t indyleg-api .
docker build -f infrastructure/docker/Dockerfile.worker -t indyleg-worker .
cd ui && docker build -t indyleg-ui .

# CDK Deploy
cd infrastructure/cdk && cdk deploy --all --context env=staging
```

---

## 8. Post-Deployment Verification

### Health Checks

```bash
# API health
curl https://{api-url}/health
# Expected: {"status": "ok", "version": "0.2.0", "timestamp": "..."}

# Metrics endpoint
curl https://{api-url}/metrics
# Expected: Prometheus text format

# OpenSearch cluster
curl https://{opensearch-url}/_cluster/health
# Expected: {"status": "green", ...}
```

### Smoke Tests

```bash
# 1. Authenticate
TOKEN=$(curl -s -X POST https://{api-url}/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}' | jq -r .access_token)

# 2. Search
curl -X POST https://{api-url}/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "summary judgment Indiana"}'

# 3. RAG Question
curl -X POST https://{api-url}/search/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the standard for summary judgment in Indiana?"}'
```

---

## 9. Rollback Procedures

### CDK Rollback

```bash
# CDK automatically rolls back failed deployments
# To manually rollback to a previous stack version:
cdk deploy --all --context env=prod --no-rollback=false

# To rollback to a specific CloudFormation snapshot:
aws cloudformation rollback-stack --stack-name IndyLeg-Api-prod
```

### Application Rollback

```bash
# Revert to previous Docker image
aws ecs update-service \
  --cluster indyleg-prod \
  --service indyleg-api \
  --task-definition indyleg-api:PREVIOUS_REVISION

# Git revert and redeploy
git revert HEAD
git push origin main
# CI/CD will deploy the reverted code
```

### Database Rollback

```bash
# Aurora supports point-in-time recovery
aws rds restore-db-cluster-to-point-in-time \
  --source-db-cluster-identifier indyleg-prod \
  --db-cluster-identifier indyleg-prod-restore \
  --restore-to-time "2026-04-15T14:00:00Z"
```

**Warning**: Database rollback may cause data loss for documents ingested after the restore point.
