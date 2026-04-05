.PHONY: dev up down test lint ingest-recent ingest-search worker ui

# ── Local Development ─────────────────────────────────────
up:  ## Start all services (Postgres, OpenSearch, LocalStack, API, Worker, UI)
	docker compose up -d

down:  ## Stop all services
	docker compose down

dev:  ## Start infra only (Postgres, OpenSearch, LocalStack) — run API/UI locally
	docker compose up -d postgres opensearch localstack

api:  ## Run API server locally (requires `make dev` first)
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

worker:  ## Run ingestion worker locally
	python -m ingestion.pipeline.worker

ui:  ## Run UI dev server locally (requires Node.js)
	cd ui && npm run dev

# ── Testing ───────────────────────────────────────────────
test:  ## Run all tests
	pytest tests/ -v --tb=short

test-unit:  ## Run unit tests only
	pytest tests/unit/ -v --tb=short

test-integration:  ## Run integration tests only
	pytest tests/integration/ -v --tb=short

# ── Lint ──────────────────────────────────────────────────
lint:  ## Run ruff + pyright
	ruff check .
	ruff format --check .
	pyright

format:  ## Auto-format code
	ruff format .
	ruff check --fix .

# ── Ingestion ─────────────────────────────────────────────
ingest-recent:  ## Ingest recent Marion County filings (last 7 days)
	python -m ingestion.cli recent --county "Marion County" --days 7

ingest-search:  ## Search and ingest (usage: make ingest-search QUERY="eviction")
	python -m ingestion.cli search --query "$(QUERY)" --county "Marion County"

ingest-case:  ## Ingest a specific case (usage: make ingest-case CASE="49D01-2401-CT-000123")
	python -m ingestion.cli case --case-number "$(CASE)"

ingest-dry:  ## Preview ingestion without queuing
	python -m ingestion.cli recent --county "Marion County" --days 7 --dry-run

# ── Docker Build ──────────────────────────────────────────
build:  ## Build all Docker images
	docker compose build

build-api:
	docker build -f infrastructure/docker/Dockerfile.api -t indyleg-api .

build-worker:
	docker build -f infrastructure/docker/Dockerfile.worker -t indyleg-worker .

build-ui:
	docker build -f ui/Dockerfile -t indyleg-ui ui/

# ── Deploy ────────────────────────────────────────────────
deploy-dev:  ## Deploy to AWS (dev)
	bash infrastructure/deploy.sh dev

deploy-prod:  ## Deploy to AWS (prod)
	bash infrastructure/deploy.sh prod

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
