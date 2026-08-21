CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS tibero_doc;

CREATE TABLE IF NOT EXISTS tibero_doc.users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE tibero_doc.users ADD COLUMN IF NOT EXISTS password_hash text;

CREATE TABLE IF NOT EXISTS tibero_doc.organizations (
    organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    created_by uuid REFERENCES tibero_doc.users(user_id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tibero_doc.workspaces (
    workspace_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES tibero_doc.organizations(organization_id) ON DELETE CASCADE,
    name text NOT NULL,
    slug text NOT NULL,
    created_by uuid REFERENCES tibero_doc.users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS tibero_doc.workspace_members (
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES tibero_doc.users(user_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('viewer', 'editor', 'manager', 'owner')),
    joined_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE TABLE IF NOT EXISTS tibero_doc.api_tokens (
    token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES tibero_doc.users(user_id) ON DELETE CASCADE,
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    name text NOT NULL DEFAULT 'cli',
    expires_at timestamptz,
    last_used_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tibero_doc.refresh_tokens (
    refresh_token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES tibero_doc.users(user_id) ON DELETE CASCADE,
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tibero_doc.groups (
    group_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    name text NOT NULL,
    created_by uuid NOT NULL REFERENCES tibero_doc.users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, name)
);

CREATE TABLE IF NOT EXISTS tibero_doc.group_members (
    group_id uuid NOT NULL REFERENCES tibero_doc.groups(group_id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES tibero_doc.users(user_id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS tibero_doc.invitations (
    invitation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    email text,
    role text NOT NULL CHECK (role IN ('viewer', 'editor', 'manager')),
    token_hash text NOT NULL UNIQUE,
    invited_by uuid NOT NULL REFERENCES tibero_doc.users(user_id),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tibero_doc.audit_logs (
    audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid REFERENCES tibero_doc.organizations(organization_id),
    workspace_id uuid REFERENCES tibero_doc.workspaces(workspace_id),
    actor_user_id uuid REFERENCES tibero_doc.users(user_id),
    action text NOT NULL,
    resource_type text,
    resource_id text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO tibero_doc.users (user_id, email, display_name)
VALUES ('00000000-0000-0000-0000-000000000001', 'local@tibero-doc.invalid', 'Local Owner')
ON CONFLICT DO NOTHING;
INSERT INTO tibero_doc.organizations (organization_id, name, slug, created_by)
VALUES ('00000000-0000-0000-0000-000000000001', 'Local Organization', 'local', '00000000-0000-0000-0000-000000000001')
ON CONFLICT DO NOTHING;
INSERT INTO tibero_doc.workspaces (workspace_id, organization_id, name, slug, created_by)
VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'Default', 'default', '00000000-0000-0000-0000-000000000001')
ON CONFLICT DO NOTHING;
INSERT INTO tibero_doc.workspace_members (workspace_id, user_id, role)
VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'owner')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS tibero_doc.documents (
    document_id text PRIMARY KEY,
    filename text NOT NULL UNIQUE,
    checksum text NOT NULL UNIQUE,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tibero_doc.documents
    ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE tibero_doc.documents
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tibero_doc.documents ADD COLUMN IF NOT EXISTS workspace_id uuid;
ALTER TABLE tibero_doc.documents ADD COLUMN IF NOT EXISTS owner_user_id uuid;
ALTER TABLE tibero_doc.documents ADD COLUMN IF NOT EXISTS visibility text NOT NULL DEFAULT 'workspace';
ALTER TABLE tibero_doc.documents ADD COLUMN IF NOT EXISTS object_key text;
UPDATE tibero_doc.documents SET workspace_id = '00000000-0000-0000-0000-000000000001' WHERE workspace_id IS NULL;
UPDATE tibero_doc.documents SET owner_user_id = '00000000-0000-0000-0000-000000000001' WHERE owner_user_id IS NULL;
ALTER TABLE tibero_doc.documents ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE tibero_doc.documents ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE tibero_doc.documents DROP CONSTRAINT IF EXISTS documents_filename_key;
ALTER TABLE tibero_doc.documents DROP CONSTRAINT IF EXISTS documents_checksum_key;
DROP INDEX IF EXISTS tibero_doc.documents_filename_idx;
CREATE UNIQUE INDEX IF NOT EXISTS documents_workspace_filename_idx ON tibero_doc.documents (workspace_id, filename);
CREATE INDEX IF NOT EXISTS documents_workspace_updated_idx ON tibero_doc.documents (workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS tibero_doc.document_acl (
    document_id text NOT NULL REFERENCES tibero_doc.documents(document_id) ON DELETE CASCADE,
    principal_type text NOT NULL CHECK (principal_type IN ('user', 'group')),
    principal_id uuid NOT NULL,
    permission text NOT NULL CHECK (permission IN ('read', 'write', 'manage')),
    granted_by uuid NOT NULL REFERENCES tibero_doc.users(user_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, principal_type, principal_id)
);

-- Document knowledge graph: entities mentioned by chunks and their relationships.
CREATE TABLE IF NOT EXISTS tibero_doc.entities (
    entity_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    entity_type text NOT NULL CHECK (entity_type IN ('person', 'organization', 'system', 'policy', 'project', 'topic')),
    name text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, entity_type, name)
);

CREATE TABLE IF NOT EXISTS tibero_doc.document_entities (
    document_id text NOT NULL REFERENCES tibero_doc.documents(document_id) ON DELETE CASCADE,
    entity_id uuid NOT NULL REFERENCES tibero_doc.entities(entity_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL,
    confidence double precision NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    mention text,
    PRIMARY KEY (document_id, entity_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS tibero_doc.relationships (
    relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES tibero_doc.workspaces(workspace_id) ON DELETE CASCADE,
    source_entity_id uuid NOT NULL REFERENCES tibero_doc.entities(entity_id) ON DELETE CASCADE,
    target_entity_id uuid NOT NULL REFERENCES tibero_doc.entities(entity_id) ON DELETE CASCADE,
    relationship_type text NOT NULL,
    confidence double precision NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    document_id text REFERENCES tibero_doc.documents(document_id) ON DELETE CASCADE,
    chunk_index integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, source_entity_id, target_entity_id, relationship_type, document_id, chunk_index),
    CHECK (source_entity_id <> target_entity_id)
);

CREATE INDEX IF NOT EXISTS entities_workspace_name_idx
    ON tibero_doc.entities (workspace_id, lower(name));
CREATE INDEX IF NOT EXISTS document_entities_entity_idx
    ON tibero_doc.document_entities (entity_id, document_id);
CREATE INDEX IF NOT EXISTS relationships_source_idx
    ON tibero_doc.relationships (workspace_id, source_entity_id);
CREATE INDEX IF NOT EXISTS relationships_target_idx
    ON tibero_doc.relationships (workspace_id, target_entity_id);

CREATE TABLE IF NOT EXISTS tibero_doc.document_versions (
    workspace_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
    filename text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    document_id text NOT NULL,
    checksum text NOT NULL,
    size_bytes bigint NOT NULL,
    chunk_count integer NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (filename, version)
);
ALTER TABLE tibero_doc.document_versions ADD COLUMN IF NOT EXISTS workspace_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001';
ALTER TABLE tibero_doc.document_versions ADD COLUMN IF NOT EXISTS object_key text;
ALTER TABLE tibero_doc.document_versions DROP CONSTRAINT IF EXISTS document_versions_pkey;
ALTER TABLE tibero_doc.document_versions ADD PRIMARY KEY (workspace_id, filename, version);

CREATE TABLE IF NOT EXISTS tibero_doc.chunks (
    document_id text NOT NULL REFERENCES tibero_doc.documents(document_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    page_number integer CHECK (page_number IS NULL OR page_number > 0),
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    PRIMARY KEY (document_id, chunk_index)
);
ALTER TABLE tibero_doc.chunks ADD COLUMN IF NOT EXISTS page_number integer;

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
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
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

ALTER TABLE tibero_doc.outbox_events
    ALTER COLUMN event_id SET DEFAULT gen_random_uuid();

CREATE INDEX IF NOT EXISTS chunk_embeddings_local_hash_idx
    ON tibero_doc.chunk_embeddings
    USING hnsw ((embedding::vector(384)) vector_cosine_ops)
    WHERE dimensions = 384;

CREATE OR REPLACE FUNCTION tibero_doc.capture_document_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO tibero_doc.outbox_events (event_type, aggregate_id, payload)
    VALUES (
        CASE WHEN TG_OP = 'DELETE' THEN 'document.deleted' ELSE 'document.upserted' END,
        COALESCE(NEW.document_id, OLD.document_id),
        jsonb_build_object(
            'operation', TG_OP,
            'filename', COALESCE(NEW.filename, OLD.filename),
            'version', COALESCE(NEW.version, OLD.version)
        )
    );
    RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS documents_outbox_trigger ON tibero_doc.documents;
CREATE TRIGGER documents_outbox_trigger
AFTER INSERT OR UPDATE OR DELETE ON tibero_doc.documents
FOR EACH ROW EXECUTE FUNCTION tibero_doc.capture_document_change();
