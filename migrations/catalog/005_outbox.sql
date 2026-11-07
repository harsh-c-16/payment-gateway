-- catalog_db outbox, copied from Aditya's shared template (shared/outbox/schema.sql) so the
-- applied, checksummed migration stays fixed if the template later changes.
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
