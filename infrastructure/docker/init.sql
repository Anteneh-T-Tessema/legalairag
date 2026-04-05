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

-- Content-hash deduplication: skip re-embedding unchanged documents
CREATE TABLE IF NOT EXISTS document_versions (
    source_id    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata     JSONB,
    PRIMARY KEY (source_id, version),
    UNIQUE (source_id, content_hash)
);

-- Citation graph edges for authority ranking
CREATE TABLE IF NOT EXISTS citation_edges (
    citing_id  TEXT NOT NULL,
    cited_id   TEXT NOT NULL,
    treatment  TEXT,  -- 'followed' | 'distinguished' | 'overruled' | 'cited'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (citing_id, cited_id)
);

CREATE INDEX IF NOT EXISTS citation_edges_cited_idx ON citation_edges (cited_id);
CREATE INDEX IF NOT EXISTS citation_edges_treatment_idx ON citation_edges (treatment);
