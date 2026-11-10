-- payments_db: Aditya owns. Isolated credentials; no cross-service FK.

CREATE TABLE IF NOT EXISTS payment_orders (
    namespace       varchar(62) NOT NULL,
    order_id        uuid        NOT NULL,
    quiesced        boolean     NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, order_id)
);

CREATE TABLE IF NOT EXISTS payment_attempts (
    namespace       varchar(62) NOT NULL,
    payment_id      uuid        NOT NULL UNIQUE,
    order_id        uuid        NOT NULL,
    attempt_number  int         NOT NULL CHECK (attempt_number BETWEEN 1 AND 2),
    status          varchar(16) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','SUCCESS','FAILED','CANCELLED','REVERSED')),
    amount_minor    bigint      NOT NULL CHECK (amount_minor >= 0),
    currency        varchar(3)  NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    failure_code    varchar(128),
    debit_id        uuid,
    reversal_id     uuid,
    created_at      timestamptz NOT NULL,
    updated_at      timestamptz NOT NULL,
    PRIMARY KEY (namespace, payment_id),
    FOREIGN KEY (namespace, order_id)
        REFERENCES payment_orders (namespace, order_id),
    UNIQUE (namespace, order_id, attempt_number)
);

-- At most one PENDING or SUCCESS attempt per order at any time.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_attempt
    ON payment_attempts (namespace, order_id)
    WHERE status IN ('PENDING', 'SUCCESS');

CREATE TABLE IF NOT EXISTS ledger_entries (
    namespace       varchar(62) NOT NULL,
    entry_id        uuid        NOT NULL,
    payment_id      uuid        NOT NULL,
    kind            varchar(16) NOT NULL CHECK (kind IN ('DEBIT', 'REVERSAL')),
    amount_minor    bigint      NOT NULL CHECK (amount_minor >= 0),
    currency        varchar(3)  NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, entry_id),
    FOREIGN KEY (namespace, payment_id)
        REFERENCES payment_attempts (namespace, payment_id)
);

-- One debit per successful payment.
CREATE UNIQUE INDEX IF NOT EXISTS one_debit_per_payment
    ON ledger_entries (namespace, payment_id)
    WHERE kind = 'DEBIT';

-- At most one reversal per successful payment.
CREATE UNIQUE INDEX IF NOT EXISTS one_reversal_per_payment
    ON ledger_entries (namespace, payment_id)
    WHERE kind = 'REVERSAL';

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
