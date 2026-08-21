ALTER TABLE tibero_doc.outbox_events ADD COLUMN IF NOT EXISTS locked_at timestamptz;
ALTER TABLE tibero_doc.outbox_events ADD COLUMN IF NOT EXISTS locked_by text;
CREATE TABLE IF NOT EXISTS tibero_doc.data_lineage_events (
 lineage_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid,
 document_id text, source_uri text, operation text NOT NULL, input_version integer,
 output_model text, job_id text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS data_lineage_document_idx ON tibero_doc.data_lineage_events(document_id,created_at DESC);
CREATE TABLE IF NOT EXISTS tibero_doc.object_lifecycle (
 object_key text PRIMARY KEY, document_id text, storage_tier text NOT NULL DEFAULT 'hot'
 CHECK(storage_tier IN ('hot','warm','cold')), last_accessed_at timestamptz NOT NULL DEFAULT now(),
 transitioned_at timestamptz NOT NULL DEFAULT now());
