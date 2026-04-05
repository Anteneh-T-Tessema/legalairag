from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from config.settings import settings
from config.logging import get_logger
from ingestion.pipeline.chunker import Chunk

logger = get_logger(__name__)

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector;"
_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS legal_chunks (
    chunk_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    section      TEXT,
    section_idx  INTEGER,
    char_start   INTEGER,
    char_end     INTEGER,
    citations    TEXT[],
    metadata     JSONB,
    content      TEXT NOT NULL,
    embedding    vector({settings.vector_dimension})
);
CREATE INDEX IF NOT EXISTS legal_chunks_source_idx ON legal_chunks (source_id);
CREATE INDEX IF NOT EXISTS legal_chunks_embedding_idx
    ON legal_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""

# Document version tracking — records every ingestion event so amendments can be detected
_CREATE_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS document_versions (
    version_id    TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_date DATE,
    is_current    BOOLEAN NOT NULL DEFAULT TRUE,
    superseded_by TEXT,            -- version_id of newer version
    metadata      JSONB
);
CREATE INDEX IF NOT EXISTS doc_versions_source_idx ON document_versions (source_id);
CREATE INDEX IF NOT EXISTS doc_versions_current_idx ON document_versions (source_id, is_current);
"""

# Citation graph persistence
_CREATE_CITATION_TABLE = """
CREATE TABLE IF NOT EXISTS citation_edges (
    edge_id       TEXT PRIMARY KEY,
    citing_id     TEXT NOT NULL,
    cited_id      TEXT NOT NULL,
    treatment     TEXT NOT NULL DEFAULT 'cited',
    is_negative   BOOLEAN NOT NULL DEFAULT FALSE,
    date_cited    DATE,
    context       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS citation_citing_idx ON citation_edges (citing_id);
CREATE INDEX IF NOT EXISTS citation_cited_idx  ON citation_edges (cited_id);
"""


class VectorIndexer:
    """
    Persists chunk embeddings into PostgreSQL + pgvector.
    Handles upserts so re-ingested documents overwrite stale chunks.
    """

    def __init__(self, database_url: str = settings.database_url) -> None:
        self._database_url = database_url
        self._conn: psycopg.AsyncConnection | None = None

    async def _get_conn(self) -> psycopg.AsyncConnection:  # type: ignore[type-arg]
        if self._conn is None or self._conn.closed:
            self._conn = await psycopg.AsyncConnection.connect(self._database_url)
            await register_vector(self._conn)
            await self._ensure_schema()
        return self._conn

    async def _ensure_schema(self) -> None:
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_EXTENSION)
            await cur.execute(_CREATE_TABLE)
            await cur.execute(_CREATE_VERSION_TABLE)
            await cur.execute(_CREATE_CITATION_TABLE)
        await conn.commit()

    async def upsert_batch(self, pairs: list[tuple[Chunk, list[float]]]) -> None:
        """Insert or update a batch of (chunk, vector) pairs."""
        if not pairs:
            return
        conn = await self._get_conn()
        import json

        rows = [
            (
                chunk.chunk_id,
                chunk.source_id,
                chunk.section_header,
                chunk.section_index,
                chunk.char_start,
                chunk.char_end,
                chunk.citations,
                json.dumps(chunk.metadata),
                chunk.text,
                vector,
            )
            for chunk, vector in pairs
        ]

        async with conn.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO legal_chunks
                    (chunk_id, source_id, section, section_idx,
                     char_start, char_end, citations, metadata, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata;
                """,
                rows,
            )
        await conn.commit()
        logger.info("upserted_chunks", count=len(pairs))

    async def delete_source(self, source_id: str) -> int:
        """Remove all chunks for a given source (e.g. re-ingestion cleanup)."""
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM legal_chunks WHERE source_id = %s RETURNING chunk_id;",
                (source_id,),
            )
            deleted = len(await cur.fetchall())
        await conn.commit()
        return deleted

    async def close(self) -> None:
        if self._conn and not self._conn.closed:
            await self._conn.close()

    # ── Document Versioning ───────────────────────────────────────────────────

    async def record_version(
        self,
        source_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """
        Record a document version and detect if the content has changed.

        Returns (version_id, is_new_version).
        is_new_version=True means the document content changed — chunks should
        be re-embedded and the previous version marked as superseded.
        """
        import json
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        version_id = f"{source_id}@{content_hash[:12]}"
        now = datetime.now(tz=timezone.utc)

        conn = await self._get_conn()
        async with conn.cursor() as cur:
            # Check if this exact version already exists
            await cur.execute(
                "SELECT version_id FROM document_versions WHERE version_id = %s",
                (version_id,),
            )
            existing = await cur.fetchone()
            if existing:
                return version_id, False  # Identical content — no re-indexing needed

            # Mark all previous versions for this source as no longer current
            await cur.execute(
                "UPDATE document_versions SET is_current = FALSE WHERE source_id = %s AND is_current = TRUE",
                (source_id,),
            )

            # Insert the new version
            effective_date = (metadata or {}).get("effective_date")
            await cur.execute(
                """
                INSERT INTO document_versions
                    (version_id, source_id, content_hash, ingested_at, effective_date, is_current, metadata)
                VALUES (%s, %s, %s, %s, %s, TRUE, %s::jsonb)
                """,
                (
                    version_id,
                    source_id,
                    content_hash,
                    now,
                    effective_date,
                    json.dumps(metadata or {}),
                ),
            )
        await conn.commit()
        logger.info(
            "document_version_recorded",
            source_id=source_id,
            version_id=version_id,
            new_version=True,
        )
        return version_id, True

    async def get_stale_sources(self, max_age_days: int = 90) -> list[str]:
        """
        Return source IDs whose embeddings are potentially stale.
        Determined by checking if a newer version exists that hasn't been re-indexed.
        """
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DISTINCT dv.source_id
                FROM document_versions dv
                WHERE dv.is_current = TRUE
                  AND dv.ingested_at < now() - make_interval(days => %s)
                  AND EXISTS (
                      SELECT 1 FROM legal_chunks lc WHERE lc.source_id = dv.source_id
                  )
                """,
                (max_age_days,),
            )
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    # ── Citation Graph Persistence ────────────────────────────────────────────

    async def upsert_citation_edge(
        self,
        citing_id: str,
        cited_id: str,
        treatment: str = "cited",
        is_negative: bool = False,
        date_cited: Any = None,
        context: str = "",
    ) -> None:
        """Persist a citation edge to the citation_edges table."""
        import json
        edge_id = hashlib.md5(f"{citing_id}->{cited_id}".encode()).hexdigest()
        conn = await self._get_conn()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO citation_edges
                    (edge_id, citing_id, cited_id, treatment, is_negative, date_cited, context)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (edge_id) DO UPDATE SET
                    treatment   = EXCLUDED.treatment,
                    is_negative = EXCLUDED.is_negative,
                    context     = EXCLUDED.context
                """,
                (edge_id, citing_id, cited_id, treatment, is_negative, date_cited, context[:500]),
            )
        await conn.commit()
