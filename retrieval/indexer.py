from __future__ import annotations

import asyncio
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
