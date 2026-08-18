CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS tibero_doc;

CREATE TABLE IF NOT EXISTS tibero_doc.documents (
    document_id text PRIMARY KEY,
    filename text NOT NULL,
    checksum text NOT NULL UNIQUE,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tibero_doc.chunks (
    document_id text NOT NULL REFERENCES tibero_doc.documents(document_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    PRIMARY KEY (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_search_vector_idx
    ON tibero_doc.chunks USING gin (search_vector);

CREATE TABLE IF NOT EXISTS tibero_doc.pipeline_jobs (
    job_id text PRIMARY KEY,
    job_type text NOT NULL,
    stage text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pipeline_jobs_status_created_idx
    ON tibero_doc.pipeline_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS tibero_doc.chunk_embeddings (
    document_id text NOT NULL,
    chunk_index integer NOT NULL,
    model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    embedding vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, chunk_index, model),
    FOREIGN KEY (document_id, chunk_index)
        REFERENCES tibero_doc.chunks(document_id, chunk_index) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tibero_doc.outbox_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    aggregate_id text NOT NULL,
    payload jsonb NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    last_error text
);

CREATE INDEX IF NOT EXISTS outbox_events_unpublished_idx
    ON tibero_doc.outbox_events (created_at)
    WHERE published_at IS NULL;
