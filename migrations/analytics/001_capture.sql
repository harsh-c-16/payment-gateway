-- M04 foundation only. NULL disposition means captured, NOT safe to commit Kafka.
CREATE TABLE bronze_captures (
    capture_id uuid PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    captured_at timestamptz NOT NULL,
    receipt jsonb NOT NULL
);

CREATE TABLE source_receipts (
    receipt_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    namespace varchar(62) NOT NULL,
    topic text NOT NULL,
    partition integer NOT NULL CHECK (partition >= 0),
    offset_number bigint NOT NULL CHECK (offset_number >= 0),
    capture_id uuid NOT NULL REFERENCES bronze_captures(capture_id),
    raw_locator varchar(128) NOT NULL,
    raw_sha256 char(64) NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    ingested_at timestamptz NOT NULL,
    bronze_durable_at timestamptz NOT NULL,
    event_id uuid,
    disposition text CHECK (disposition IN
        ('new_valid', 'duplicate_delivery', 'invalid', 'redelivery_noop')),
    reason_code text,
    silver_committed_observed_at timestamptz,
    gold_visible_at timestamptz,
    visibility_generation bigint CHECK (visibility_generation > 0),
    timing_validity text NOT NULL DEFAULT 'missing'
        CHECK (timing_validity IN ('observed', 'missing', 'recovery_upper_bound')),
    PRIMARY KEY (namespace, topic, partition, offset_number),
    CHECK ((gold_visible_at IS NULL) = (visibility_generation IS NULL)),
    CHECK (disposition IS NOT NULL OR
        (event_id IS NULL AND reason_code IS NULL AND silver_committed_observed_at IS NULL
         AND gold_visible_at IS NULL AND visibility_generation IS NULL
         AND timing_validity = 'missing'))
);

CREATE INDEX source_receipts_namespace_cursor ON source_receipts(namespace, receipt_sequence);

CREATE TABLE quarantine (
    quarantine_id uuid PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    topic text NOT NULL,
    partition integer NOT NULL,
    offset_number bigint NOT NULL,
    raw_locator varchar(128) NOT NULL,
    raw_sha256 char(64) NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    reason_code text NOT NULL,
    validation_path text,
    diagnostic_message text NOT NULL,
    first_seen_at timestamptz NOT NULL,
    schema_version integer CHECK (schema_version > 0),
    transform_version varchar(128) NOT NULL,
    repair_status text NOT NULL DEFAULT 'unrepaired'
        CHECK (repair_status IN ('unrepaired', 'repaired')),
    repair_reference varchar(128),
    FOREIGN KEY (namespace, topic, partition, offset_number)
        REFERENCES source_receipts(namespace, topic, partition, offset_number)
);

CREATE TABLE processing_runs (
    run_id uuid PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    transform_version varchar(128) NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED'))
);

-- No substitute outbox: Aditya supplies its DDL/library before M05 dispositions.
