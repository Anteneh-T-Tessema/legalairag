# Changelog

All notable changes to the Indiana Legal RAG Platform are documented here.

## [0.6.0] — 2026-04-05

### Tests (0.6.0)
- Comprehensive unit test coverage — 428 Python tests + 54 UI tests, all passing
- 12 new Python test files covering all previously uncovered modules
- 4 new React/Vitest component tests (ResultCard, ChatInterface, SearchResults, DocumentUpload)
- Fixed 13 failing tests (Chunk constructor, regex patterns, mock paths, CLI bug, Python 3.9 compat)

### Bug Fixes (0.6.0)
- `cli.py`: fixed `document_url` → `download_url` field access (3 sites)
- `embedder.py`: use `zip(strict=False)` for Python 3.9 compatibility
- Dockerfiles: corrected build order and `.dockerignore`
- Auth blacklist: TTL-based eviction to prevent memory leak
- Rate limiter: Redis reconnection on transient failures

## [0.5.0] — 2026-04-05

### Features (0.5.0)
- Ecosystem source connectors — Protection Orders, Court Stats, E-Filing, BMV, ECRW clients
- MyCaseClient tests, audit log persistence, CI coverage gating
- Indiana Courts ecosystem integration — `mycase.in.gov` client
- Redis rate limiting, token revocation & refresh rotation
- Secrets management, observability metrics, UI tests
- Complete UI fraud analysis, Docker local dev, CI/CD production hardening

### Documentation (0.5.0)
- Light-theme architecture overview SVG
- Visual documentation — SVG diagrams, hero README, GitHub community files, GLOSSARY
- Comprehensive system documentation suite (ARCHITECTURE, SECURITY, DEPLOYMENT, etc.)
- Sharpen README — Quick Start, rate-limit headers, changelog section

### Tests (0.5.0)
- 43 API router + middleware tests, StrEnum/refresh compat fixes
- 48 unit tests for validator, query_parser, reranker, base_agent
- 32 tests for ecosystem source connectors

### Bug Fixes (0.5.0)
- Remove duplicate `Role` class, lint errors, obsolete docker-compose version
- HMAC key default to 32 bytes
- Wire adaptive weights + version-check + fraud API
- Resolve all Pyright/ruff errors, fix `authority.rank` → `rerank` bug, Python 3.9 compat

## [0.1.0] — 2026-04-04

### Features (0.1.0)
- Initial scaffold of Indiana Legal RAG Platform
- Complete platform build-out — UI, auth, CI/CD, ingestion CLI, CDK infrastructure
- Production-grade RAG enhancements (hybrid search, reranking, authority scoring)
