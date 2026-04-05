"""Unit tests for retrieval.indexer – VectorIndexer."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingestion.pipeline.chunker import Chunk

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _chunk(chunk_id: str = "c-1", source_id: str = "src-1", text: str = "text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_id=source_id,
        text=text,
        section_header="§ 1",
        section_index=0,
        char_start=0,
        char_end=len(text),
        citations=["IC 35-42-1-1"],
        metadata={"court": "ind"},
    )


def _mock_conn():
    """Return an AsyncMock that behaves like psycopg.AsyncConnection."""
    conn = AsyncMock()
    conn.closed = False
    cursor = AsyncMock()
    # conn.cursor() is used as ``async with conn.cursor() as cur:``
    # Must be a sync call returning an async-context-manager.
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=cursor)
    ctx.__aexit__ = AsyncMock(return_value=False)
    conn.cursor = MagicMock(return_value=ctx)
    return conn, cursor


# ── Construction ──────────────────────────────────────────────────────────────


class TestConstruction:
    def test_default_database_url(self):
        with patch("retrieval.indexer.settings") as mock_settings:
            mock_settings.database_url = "postgresql://localhost/test"
            mock_settings.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer(database_url="postgresql://localhost/test")
            assert indexer._database_url == "postgresql://localhost/test"
            assert indexer._conn is None


# ── upsert_batch ──────────────────────────────────────────────────────────────


class TestUpsertBatch:
    @pytest.mark.asyncio
    async def test_empty_batch_is_noop(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            # Should not touch the database at all
            await indexer.upsert_batch([])

    @pytest.mark.asyncio
    async def test_upsert_calls_executemany(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn

            chunk = _chunk()
            vec = [0.1] * 1024
            await indexer.upsert_batch([(chunk, vec)])

            cursor.executemany.assert_awaited_once()
            conn.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_upsert_row_contains_chunk_fields(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn

            chunk = _chunk(chunk_id="c-42", source_id="src-7", text="hello world")
            vec = [0.5] * 1024
            await indexer.upsert_batch([(chunk, vec)])

            args = cursor.executemany.call_args
            rows = args[0][1]
            assert rows[0][0] == "c-42"
            assert rows[0][1] == "src-7"
            assert rows[0][8] == "hello world"
            assert rows[0][9] == vec


# ── delete_source ─────────────────────────────────────────────────────────────


class TestDeleteSource:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn
            cursor.fetchall.return_value = [("c-1",), ("c-2",), ("c-3",)]

            count = await indexer.delete_source("src-1")
            assert count == 3
            cursor.execute.assert_awaited()
            conn.commit.assert_awaited()


# ── record_version ────────────────────────────────────────────────────────────


class TestRecordVersion:
    @pytest.mark.asyncio
    async def test_existing_version_returns_false(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn

            content = "IC 35-42-1-1 Murder statute"
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            expected_vid = f"src-1@{content_hash[:12]}"

            # Simulate version already in DB
            cursor.fetchone.return_value = (expected_vid,)

            vid, is_new = await indexer.record_version("src-1", content)
            assert vid == expected_vid
            assert is_new is False

    @pytest.mark.asyncio
    async def test_new_version_returns_true(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn
            cursor.fetchone.return_value = None  # Not in DB yet

            vid, is_new = await indexer.record_version(
                "src-1", "new content", metadata={"effective_date": "2025-01-01"}
            )
            assert is_new is True
            assert vid.startswith("src-1@")
            conn.commit.assert_awaited()


# ── close ─────────────────────────────────────────────────────────────────────


class TestClose:
    @pytest.mark.asyncio
    async def test_close_when_connected(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn = AsyncMock()
            conn.closed = False
            indexer._conn = conn

            await indexer.close()
            conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            # No exception when _conn is None
            await indexer.close()


# ── upsert_citation_edge ─────────────────────────────────────────────────────


class TestUpsertCitationEdge:
    @pytest.mark.asyncio
    async def test_persists_edge(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn

            await indexer.upsert_citation_edge(
                citing_id="case-A",
                cited_id="case-B",
                treatment="followed",
                is_negative=False,
                context="relying on precedent",
            )
            cursor.execute.assert_awaited_once()
            conn.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_context_truncated_to_500(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn

            long_context = "x" * 1000
            await indexer.upsert_citation_edge("a", "b", context=long_context)

            args = cursor.execute.call_args[0][1]
            assert len(args[-1]) == 500


# ── get_stale_sources ─────────────────────────────────────────────────────────


class TestGetStaleSources:
    @pytest.mark.asyncio
    async def test_returns_source_ids(self):
        with patch("retrieval.indexer.settings") as s:
            s.database_url = "postgresql://localhost/test"
            s.vector_dimension = 1024
            from retrieval.indexer import VectorIndexer

            indexer = VectorIndexer()
            conn, cursor = _mock_conn()
            indexer._conn = conn
            cursor.fetchall.return_value = [("src-old-1",), ("src-old-2",)]

            stale = await indexer.get_stale_sources(max_age_days=30)
            assert stale == ["src-old-1", "src-old-2"]
