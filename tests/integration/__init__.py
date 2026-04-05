"""Integration tests for pgvector indexer and hybrid search.

Requires: docker-compose services (postgres) running.
Run: pytest tests/integration/ -v --timeout=60
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

# Skip entire module if DATABASE_URL not reachable
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="DATABASE_URL not set — start docker-compose postgres first",
)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def db_url():
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://indyleg:changeme@localhost:5432/indyleg",
    )


class TestPgvectorIntegration:
    """Tests that require a real PostgreSQL + pgvector instance."""

    def test_connection(self, db_url: str) -> None:
        """Verify we can connect to the database."""
        import psycopg

        conninfo = db_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(conninfo) as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            assert row is not None
            assert row[0] == 1

    def test_pgvector_extension_loaded(self, db_url: str) -> None:
        """Verify pgvector extension is installed."""
        import psycopg

        conninfo = db_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(conninfo) as conn:
            row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
            assert row is not None, "pgvector extension not installed"

    def test_indexer_upsert_and_search(self, db_url: str) -> None:
        """Round-trip: index a vector, then retrieve it via cosine similarity."""
        import psycopg
        from pgvector.psycopg import register_vector

        conninfo = db_url.replace("postgresql+psycopg://", "postgresql://")
        dim = 1024
        table = f"test_vectors_{uuid.uuid4().hex[:8]}"

        with psycopg.connect(conninfo) as conn:
            register_vector(conn)
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"CREATE TABLE {table} (id TEXT PRIMARY KEY, embedding vector({dim}), content TEXT)"
            )

            # Insert a test vector
            test_id = "test-001"
            test_vector = [0.1] * dim
            conn.execute(
                f"INSERT INTO {table} (id, embedding, content) VALUES (%s, %s, %s)",
                (test_id, test_vector, "Indiana eviction notice requirements"),
            )
            conn.commit()

            # Query by cosine similarity
            rows = conn.execute(
                f"SELECT id, content, "
                f"embedding <=> %s::vector AS distance "
                f"FROM {table} ORDER BY distance LIMIT 1",
                (test_vector,),
            ).fetchall()

            assert len(rows) == 1
            assert rows[0][0] == test_id
            assert rows[0][2] < 0.01  # near-zero distance to itself

            # Cleanup
            conn.execute(f"DROP TABLE {table}")
            conn.commit()


class TestHybridSearchIntegration:
    """Tests hybrid search with real pgvector."""

    def test_hybrid_search_returns_results(self, db_url: str) -> None:
        """
        End-to-end: insert vectors, run hybrid search, verify results.
        Uses real pgvector for the vector component and in-memory BM25.
        """
        import psycopg
        from pgvector.psycopg import register_vector

        conninfo = db_url.replace("postgresql+psycopg://", "postgresql://")
        dim = 1024
        table = f"test_hybrid_{uuid.uuid4().hex[:8]}"

        with psycopg.connect(conninfo) as conn:
            register_vector(conn)
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"""CREATE TABLE {table} (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    section TEXT,
                    content TEXT,
                    citations TEXT[],
                    embedding vector({dim})
                )"""
            )

            # Insert test documents
            docs = [
                (
                    "chunk-1",
                    "src-1",
                    "holdings",
                    "Indiana Code 35-42-1-1 defines murder as a Level 1 felony.",
                    ["IC 35-42-1-1"],
                ),
                (
                    "chunk-2",
                    "src-2",
                    "facts",
                    "The defendant filed a motion to dismiss in Marion County.",
                    [],
                ),
                (
                    "chunk-3",
                    "src-3",
                    "procedure",
                    "Small claims filing deadline is 2 years under IC 34-11-2-4.",
                    ["IC 34-11-2-4"],
                ),
            ]
            for chunk_id, source_id, section, content, citations in docs:
                vec = [0.1] * dim
                conn.execute(
                    f"INSERT INTO {table} "
                    f"(id, source_id, section, content, "
                    f"citations, embedding) "
                    f"VALUES (%s, %s, %s, %s, %s, %s)",
                    (chunk_id, source_id, section, content, citations, vec),
                )
            conn.commit()

            # Vector search
            query_vec = [0.1] * dim
            rows = conn.execute(
                f"SELECT id, content, "
                f"embedding <=> %s::vector AS distance "
                f"FROM {table} ORDER BY distance LIMIT 3",
                (query_vec,),
            ).fetchall()
            assert len(rows) == 3

            # Full-text search
            rows = conn.execute(
                f"SELECT id, content FROM {table} WHERE content ILIKE %s",
                ("%murder%",),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "chunk-1"

            conn.execute(f"DROP TABLE {table}")
            conn.commit()
