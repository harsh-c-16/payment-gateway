-- inventory_db: Aditya owns. Isolated credentials; no cross-service FK.

CREATE TABLE IF NOT EXISTS inventory (
    namespace       varchar(62) NOT NULL,
    sku             varchar(64) NOT NULL CHECK (sku ~ '^[!-~]{1,64}$'),
    on_hand         bigint      NOT NULL CHECK (on_hand >= 0),
    reserved        bigint      NOT NULL CHECK (reserved >= 0),
    stock_version   bigint      NOT NULL CHECK (stock_version >= 1),
    changed_at      timestamptz NOT NULL,
    PRIMARY KEY (namespace, sku),
    CHECK (reserved <= on_hand)
);

CREATE TABLE IF NOT EXISTS reservations (
    namespace       varchar(62) NOT NULL,
    reservation_id  uuid        NOT NULL UNIQUE,
    order_id        uuid        NOT NULL,
    state           varchar(16) NOT NULL DEFAULT 'ACTIVE'
        CHECK (state IN ('ACTIVE','COMMITTED','RELEASED','EXPIRED')),
    expires_at      timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, order_id),
    UNIQUE (namespace, reservation_id)
);

CREATE INDEX IF NOT EXISTS reservations_expiry ON reservations (expires_at)
    WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS reservation_items (
    namespace       varchar(62) NOT NULL,
    reservation_id  uuid        NOT NULL,
    sku             varchar(64) NOT NULL CHECK (sku ~ '^[!-~]{1,64}$'),
    quantity        smallint    NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    PRIMARY KEY (namespace, reservation_id, sku),
    FOREIGN KEY (namespace, reservation_id)
        REFERENCES reservations (namespace, reservation_id)
);

CREATE TABLE IF NOT EXISTS inventory_seeds (
    namespace       varchar(62)  NOT NULL,
    seed_id         uuid         NOT NULL,
    manifest_hash   char(64)     NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    profile_hash    char(64)     NOT NULL CHECK (profile_hash ~ '^[0-9a-f]{64}$'),
    status          varchar(16)  NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING','COMPLETE','FAILED')),
    sku_count       int          NOT NULL DEFAULT 0,
    created_skus    int          NOT NULL DEFAULT 0,
    unchanged_skus  int          NOT NULL DEFAULT 0,
    created_at      timestamptz  NOT NULL DEFAULT clock_timestamp(),
    completed_at    timestamptz,
    PRIMARY KEY (namespace, seed_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS seeds_manifest ON inventory_seeds (namespace, manifest_hash, profile_hash)
    WHERE status = 'COMPLETE';

CREATE TABLE IF NOT EXISTS inventory_seed_chunks (
    namespace       varchar(62) NOT NULL,
    seed_id         uuid        NOT NULL,
    chunk_no        int         NOT NULL CHECK (chunk_no >= 0),
    sku_count       int         NOT NULL CHECK (sku_count >= 0),
    completed_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, seed_id, chunk_no),
    FOREIGN KEY (namespace, seed_id)
        REFERENCES inventory_seeds (namespace, seed_id)
);

-- Cancellation tombstones: order_id in reservations with state='RELEASED'
-- serves as a tombstone. A delayed reserve for that order_id will find
-- the existing row and fail.

CREATE TABLE IF NOT EXISTS operation_keys (
    namespace       varchar(62)  NOT NULL,
    user_id         varchar(128) NOT NULL,
    operation       varchar(64)  NOT NULL,
    key             varchar(128) NOT NULL CHECK (length(key) BETWEEN 1 AND 128),
    request_hash    char(64)     NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    response        jsonb        NOT NULL CHECK (jsonb_typeof(response) = 'object'),
    created_at      timestamptz  NOT NULL,
    PRIMARY KEY (namespace, user_id, operation, key)
);

CREATE TABLE IF NOT EXISTS local_diagnostics (
    namespace                     varchar(62)  NOT NULL,
    diagnostic_id                 uuid         NOT NULL,
    run_id                        varchar(128) NOT NULL,
    source_service                varchar(32)  NOT NULL,
    reason_code                   varchar(128) NOT NULL,
    correlation_id                uuid         NOT NULL,
    created_at                    timestamptz  NOT NULL,
    content_hash                  char(64)     NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    restricted_content_reference  varchar(128) NOT NULL,
    source_coordinates            jsonb,
    record_sha256                 char(64)     NOT NULL CHECK (record_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (namespace, diagnostic_id)
);

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id       bigserial    PRIMARY KEY,
    event_id        uuid         NOT NULL UNIQUE,
    namespace       varchar(62)  NOT NULL,
    aggregate_type  varchar(32)  NOT NULL,
    aggregate_id    varchar(128) NOT NULL,
    topic           varchar(256) NOT NULL,
    partition_key   varchar(256) NOT NULL,
    payload         bytea        NOT NULL,
    headers         jsonb        NOT NULL DEFAULT '[]',
    schema_subject  varchar(256),
    produced_at     timestamptz  NOT NULL,
    published_at    timestamptz,
    relay_claim     uuid,
    relay_claimed_at timestamptz,
    created_at      timestamptz  NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (outbox_id)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS outbox_aggregate ON outbox (namespace, aggregate_type, aggregate_id, outbox_id);
