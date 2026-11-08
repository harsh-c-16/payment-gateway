-- Template: each database owner includes this in its own migration.
-- The outbox stores serialised immutable events for at-least-once relay to Kafka.
CREATE TABLE IF NOT EXISTS outbox (
    outbox_id        bigserial    PRIMARY KEY,
    event_id         uuid         NOT NULL UNIQUE,
    namespace        varchar(62)  NOT NULL,
    aggregate_type   varchar(32)  NOT NULL,
    aggregate_id     varchar(128) NOT NULL,
    topic            varchar(256) NOT NULL,
    partition_key    varchar(256) NOT NULL,
    payload          bytea        NOT NULL,
    headers          jsonb        NOT NULL DEFAULT '[]',
    schema_subject   varchar(256),
    produced_at      timestamptz  NOT NULL,
    published_at     timestamptz,
    relay_claim      uuid,
    relay_claimed_at timestamptz,
    created_at       timestamptz  NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (outbox_id)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS outbox_aggregate
    ON outbox (namespace, aggregate_type, aggregate_id, outbox_id);

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

-- Private synthetic model diagnostics. Never exposed by an API, log or event.
-- m1-turn:<turn_id> references the turn's finite intent_diagnostic and this
-- optional bounded raw output. Only M1's database role should have access.
CREATE TABLE intent_rejections (
    namespace varchar(62) NOT NULL,
    turn_id uuid NOT NULL,
    restricted_output text NOT NULL CHECK (octet_length(restricted_output) <= 65536),
    PRIMARY KEY (namespace, turn_id),
    FOREIGN KEY (namespace, turn_id) REFERENCES turns(namespace, turn_id)
);
