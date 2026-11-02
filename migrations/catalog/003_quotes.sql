-- Immutable quotes and scoped idempotency keys.
CREATE TABLE operation_keys (
    namespace varchar(62) NOT NULL,
    scope varchar(128) NOT NULL,
    operation varchar(32) NOT NULL,
    key varchar(128) NOT NULL,
    request_hash char(64) NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, scope, operation, key)
);

CREATE TABLE quotes (
    namespace varchar(62) NOT NULL,
    quote_id uuid NOT NULL,
    user_id varchar(128) NOT NULL,
    cart_id uuid NOT NULL,
    cart_version bigint NOT NULL CHECK (cart_version >= 0),
    total_amount_minor bigint NOT NULL CHECK (total_amount_minor >= 0),
    currency char(3) NOT NULL CHECK (currency = 'INR'),
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (namespace, quote_id),
    CHECK (expires_at > created_at)
);

CREATE TABLE quote_lines (
    namespace varchar(62) NOT NULL,
    quote_id uuid NOT NULL,
    sku varchar(64) NOT NULL,
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    unit_price_minor bigint NOT NULL CHECK (unit_price_minor BETWEEN 1 AND 1000000000),
    line_total_minor bigint NOT NULL CHECK (line_total_minor = unit_price_minor * quantity),
    catalog_version bigint NOT NULL CHECK (catalog_version >= 1),
    PRIMARY KEY (namespace, quote_id, sku),
    FOREIGN KEY (namespace, quote_id) REFERENCES quotes
);
