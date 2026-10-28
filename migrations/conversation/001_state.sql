-- M1-owned state only. Shared outbox/diagnostic DDL awaits its owners' templates.
CREATE TABLE sessions (
    namespace varchar(62) NOT NULL,
    session_id uuid NOT NULL,
    user_id varchar(128) NOT NULL,
    event_version bigint NOT NULL DEFAULT 0 CHECK (event_version >= 0),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (namespace, session_id),
    UNIQUE (namespace, session_id, user_id)
);

CREATE TABLE carts (
    namespace varchar(62) NOT NULL,
    cart_id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id varchar(128) NOT NULL,
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at timestamptz NOT NULL,
    quote_id uuid,
    quote_cart_version bigint,
    confirmation_id uuid,
    PRIMARY KEY (namespace, cart_id),
    UNIQUE (namespace, session_id),
    FOREIGN KEY (namespace, session_id, user_id)
        REFERENCES sessions (namespace, session_id, user_id),
    CHECK ((quote_id IS NULL AND quote_cart_version IS NULL AND confirmation_id IS NULL)
        OR (quote_id IS NOT NULL AND quote_cart_version IS NOT NULL
            AND quote_cart_version = version))
);

CREATE TABLE cart_items (
    namespace varchar(62) NOT NULL,
    cart_id uuid NOT NULL,
    sku varchar(64) NOT NULL CHECK (sku ~ '^[!-~]{1,64}$'),
    quantity smallint NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    display_price_minor bigint CHECK (display_price_minor >= 0),
    PRIMARY KEY (namespace, cart_id, sku),
    FOREIGN KEY (namespace, cart_id) REFERENCES carts (namespace, cart_id)
);

CREATE TABLE turns (
    namespace varchar(62) NOT NULL,
    request_id uuid NOT NULL,
    turn_id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id varchar(128) NOT NULL,
    request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    response jsonb NOT NULL CHECK (jsonb_typeof(response) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (namespace, request_id),
    UNIQUE (namespace, turn_id),
    FOREIGN KEY (namespace, session_id, user_id)
        REFERENCES sessions (namespace, session_id, user_id)
);

CREATE TABLE operation_keys (
    namespace varchar(62) NOT NULL,
    user_id varchar(128) NOT NULL,
    operation varchar(64) NOT NULL,
    key varchar(128) NOT NULL CHECK (length(key) BETWEEN 1 AND 128),
    request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    response jsonb NOT NULL CHECK (jsonb_typeof(response) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (namespace, user_id, operation, key)
);
