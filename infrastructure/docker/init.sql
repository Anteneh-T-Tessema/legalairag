CREATE EXTENSION IF NOT EXISTS vector;

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
    embedding    vector(1024)
);

CREATE INDEX IF NOT EXISTS legal_chunks_source_idx ON legal_chunks (source_id);
