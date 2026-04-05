FROM python:3.11-slim

WORKDIR /app

# Copy dependency spec first for layer caching
COPY pyproject.toml .

# Copy source code (needed by pip install .)
COPY agents/ agents/
COPY api/ api/
COPY config/ config/
COPY generation/ generation/
COPY ingestion/ ingestion/
COPY retrieval/ retrieval/

RUN pip install --no-cache-dir .

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
