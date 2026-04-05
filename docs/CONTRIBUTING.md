# Contributing to IndyLeg

Thank you for your interest in contributing to IndyLeg! This document provides guidelines and best practices.

---

## Getting Started

1. **Fork and clone** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Set up the development environment** (see [README — Local Development](../README.md#10-local-development))

---

## Development Workflow

### 1. Install Dependencies

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### 2. Start Local Services

```bash
docker compose up -d
```

### 3. Make Changes

- Follow the existing code style (enforced by ruff)
- All new Python code must be async-compatible
- Use type annotations for all function signatures
- Use `from __future__ import annotations` at the top of every module

### 4. Run Tests

```bash
# Unit tests (fast, no external services)
pytest tests/unit/ -v

# Full suite
pytest tests/ -v
```

### 5. Run Linting

```bash
ruff check .
ruff format .
pyright
```

### 6. Commit and Push

Write clear commit messages:
```
feat: add property transfer velocity detector to fraud agent
fix: correct RRF zero-score edge case in hybrid search
docs: add fraud detection architecture guide
test: add integration tests for pgvector cosine search
```

---

## Code Style

### Python

- **Linter**: ruff (line length 100)
- **Type checker**: Pyright (basic mode)
- **Target**: Python 3.11+ syntax, 3.9+ compatible via `from __future__ import annotations`
- No `Any` types without an explanatory comment
- Prefer `dataclass` for data containers
- Use structlog for all logging (via `config.logging.get_logger`)

### TypeScript

- `strict: true` in `tsconfig.json`
- No `any` types without justification

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation changes
- `test:` — new or updated tests
- `refactor:` — code restructuring without behavior change
- `chore:` — build, CI, dependency updates

---

## Adding New Features

### New Agent

1. Create `agents/your_agent.py` extending `BaseAgent`
2. Declare `allowed_tools` for tool access control
3. Implement `_execute(**kwargs)` method
4. Add unit tests in `tests/unit/test_your_agent.py`
5. Add API router in `api/routers/` if the agent needs an HTTP endpoint
6. Add request/response schemas in `api/schemas/`
7. Document in README under "Subsystem Deep Dives"

### New Pattern Detector (Fraud)

1. Add a `_detect_*` static method to `_FilingPatternAnalyzer`
2. Register it in the `analyze()` method
3. Add tests in `tests/unit/test_fraud_detection.py`
4. Document the detector in `docs/FRAUD_DETECTION.md`

### New Retrieval Feature

1. Add to the appropriate module in `retrieval/`
2. Ensure it returns `list[SearchResult]` for pipeline compatibility
3. Add unit tests with mock data
4. Update the architecture docs if it changes the pipeline flow

### New Public Data Source

1. Add client class to `ingestion/sources/public_resource.py`
2. Return `PublicLegalOpinion` or `IndianaStatute` for pipeline compatibility
3. Respect rate limits — use `asyncio.Semaphore` and exponential backoff
4. Add integration tests

---

## Testing Requirements

- All new code must have unit tests
- Integration tests for any new external service interactions
- Test edge cases: empty inputs, missing metadata, malformed dates
- Mock all external services in unit tests (Bedrock, PostgreSQL, SQS)
- Use `pytest-asyncio` for async test functions

---

## Pull Request Checklist

Before submitting your PR, verify:

- [ ] All unit tests pass: `pytest tests/unit/ -v`
- [ ] Linting passes: `ruff check .`
- [ ] Format is correct: `ruff format --check .`
- [ ] Type checking passes: `pyright`
- [ ] TypeScript compiles: `cd ui && npx tsc --noEmit`
- [ ] New features have tests
- [ ] Documentation updated (README, docs/)
- [ ] Commit messages follow conventional format

---

## Architecture Overview

For a high-level understanding of the system, see:
- [Architecture Guide](ARCHITECTURE.md)
- [Fraud Detection Deep Dive](FRAUD_DETECTION.md)
- [API Reference](API.md)
- [Testing Guide](TESTING.md)
