-- Stock read model fed by Inventory events, plus the shared local diagnostics template.
-- Latest absolute snapshot per SKU. available is derived, never a separately mutable counter.
CREATE TABLE stock_projection (
    namespace varchar(62) NOT NULL,
    sku varchar(64) NOT NULL,
    on_hand bigint NOT NULL,
    reserved bigint NOT NULL,
    available bigint GENERATED ALWAYS AS (on_hand - reserved) STORED,
    stock_version bigint NOT NULL CHECK (stock_version >= 1),
    changed_at timestamptz NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    event_id uuid NOT NULL,
    PRIMARY KEY (namespace, sku),
    CHECK (0 <= reserved AND reserved <= on_hand)
);

CREATE TABLE projection_event_ids (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    content_hash char(64) NOT NULL,
    PRIMARY KEY (namespace, event_id)
);

CREATE TABLE projection_receipts (
    namespace varchar(62) NOT NULL,
    topic varchar(128) NOT NULL,
    partition integer NOT NULL,
    "offset" bigint NOT NULL,
    event_id uuid,
    sku varchar(64),
    outcome varchar(16) NOT NULL
        CHECK (outcome IN ('applied', 'duplicate', 'stale', 'conflict', 'deferred', 'invalid')),
    previous_version bigint,
    current_version bigint,
    version_gap boolean NOT NULL DEFAULT false,
    produced_at timestamptz,
    observed_commit_at timestamptz,
    sequence bigint GENERATED ALWAYS AS IDENTITY,
    PRIMARY KEY (namespace, topic, partition, "offset")
);
CREATE UNIQUE INDEX projection_receipts_cursor ON projection_receipts (namespace, sequence);

-- A snapshot for a SKU not yet in the catalogue stays durable until reconciliation applies it.
CREATE TABLE stock_deferred (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    sku varchar(64) NOT NULL,
    on_hand bigint NOT NULL,
    reserved bigint NOT NULL,
    stock_version bigint NOT NULL,
    changed_at timestamptz NOT NULL,
    deferred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, event_id)
);
CREATE INDEX stock_deferred_sku ON stock_deferred (namespace, sku);

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
