-- Template only: each database owner includes this in its own migrations.
-- No raw model output, free-form text or credentials belong in this table.
CREATE TABLE IF NOT EXISTS local_diagnostics (
    namespace varchar(62) NOT NULL,
    diagnostic_id uuid NOT NULL,
    run_id varchar(128) NOT NULL,
    source_service varchar(32) NOT NULL,
    reason_code varchar(128) NOT NULL,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    content_hash char(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    restricted_content_reference varchar(128) NOT NULL,
    source_coordinates jsonb,
    record_sha256 char(64) NOT NULL CHECK (record_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (namespace, diagnostic_id)
);
