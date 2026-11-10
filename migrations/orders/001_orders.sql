-- orders_db: Aditya owns. Isolated credentials; no cross-service FK.

CREATE TABLE IF NOT EXISTS orders (
    namespace       varchar(62)  NOT NULL,
    order_id        uuid         NOT NULL,
    order_version   bigint       NOT NULL DEFAULT 1 CHECK (order_version >= 1),
    status          varchar(24)  NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING','RESERVING','PAYMENT_PENDING',
            'COMMITTING_STOCK','CONFIRMED',
            'COMPENSATING','CANCELLED','MANUAL_REVIEW'
        )),
    quote_id        uuid         NOT NULL,
    user_id         varchar(128) NOT NULL,
    session_id      uuid         NOT NULL,
    total_amount_minor bigint    NOT NULL CHECK (total_amount_minor >= 0),
    currency        varchar(3)   NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    reservation_id  uuid,
    payment_id      uuid,
    failure_code    varchar(128),
    created_at      timestamptz  NOT NULL,
    updated_at      timestamptz  NOT NULL,
    PRIMARY KEY (namespace, order_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS orders_quote_user
    ON orders (namespace, user_id, quote_id);

CREATE TABLE IF NOT EXISTS order_items (
    namespace       varchar(62) NOT NULL,
    order_id        uuid        NOT NULL,
    sku             varchar(64) NOT NULL CHECK (sku ~ '^[!-~]{1,64}$'),
    quantity        smallint    NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    unit_price_minor bigint     NOT NULL CHECK (unit_price_minor >= 1),
    line_total_minor bigint     NOT NULL CHECK (line_total_minor >= 1),
    catalog_version bigint      NOT NULL CHECK (catalog_version >= 1),
    PRIMARY KEY (namespace, order_id, sku),
    FOREIGN KEY (namespace, order_id) REFERENCES orders (namespace, order_id)
);

CREATE TABLE IF NOT EXISTS saga_jobs (
    namespace       varchar(62) NOT NULL,
    order_id        uuid        NOT NULL,
    planned_step    varchar(32) NOT NULL
        CHECK (planned_step IN (
            'RESERVE','AUTHORIZE_PAYMENT','COMMIT_STOCK',
            'CONFIRM','COMPENSATE_RELEASE','COMPENSATE_PAYMENT','CANCEL'
        )),
    attempt         int         NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    next_attempt_at timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, order_id),
    FOREIGN KEY (namespace, order_id) REFERENCES orders (namespace, order_id)
);

CREATE INDEX IF NOT EXISTS saga_pending ON saga_jobs (next_attempt_at)
    WHERE next_attempt_at IS NOT NULL;

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
    outbox_id       bigserial   PRIMARY KEY,
    event_id        uuid        NOT NULL UNIQUE,
    namespace       varchar(62) NOT NULL,
    aggregate_type  varchar(32) NOT NULL,
    aggregate_id    varchar(128) NOT NULL,
    topic           varchar(256) NOT NULL,
    partition_key   varchar(256) NOT NULL,
    payload         bytea       NOT NULL,
    headers         jsonb       NOT NULL DEFAULT '[]',
    schema_subject  varchar(256),
    produced_at     timestamptz NOT NULL,
    published_at    timestamptz,
    relay_claim     uuid,
    relay_claimed_at timestamptz,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (outbox_id)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS outbox_aggregate ON outbox (namespace, aggregate_type, aggregate_id, outbox_id);
