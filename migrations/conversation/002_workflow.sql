-- M1 command journal: persist remote identity before issuing a mutation.
ALTER TABLE carts ADD COLUMN quote_payload jsonb;
CREATE TABLE confirmations (
    namespace varchar(62) NOT NULL,
    user_id varchar(128) NOT NULL,
    confirmation_id uuid NOT NULL,
    cart_id uuid NOT NULL,
    quote_id uuid NOT NULL,
    cart_version bigint NOT NULL,
    PRIMARY KEY(namespace,user_id,confirmation_id),
    FOREIGN KEY(namespace,cart_id) REFERENCES carts(namespace,cart_id)
);
CREATE TABLE workflow_commands (
    namespace varchar(62) NOT NULL,
    user_id varchar(128) NOT NULL,
    operation varchar(64) NOT NULL,
    key varchar(128) NOT NULL,
    cart_id uuid NOT NULL,
    request_hash char(64) NOT NULL,
    business_input jsonb NOT NULL,
    provider_input jsonb NOT NULL,
    provider_context jsonb NOT NULL,
    remote_key varchar(128) NOT NULL,
    state varchar(16) NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'complete', 'rejected')),
    response jsonb,
    error jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace,user_id,operation,key),
    FOREIGN KEY (namespace,cart_id) REFERENCES carts(namespace,cart_id),
    CHECK ((state='pending' AND response IS NULL AND error IS NULL)
        OR (state='complete' AND response IS NOT NULL AND error IS NULL)
        OR (state='rejected' AND response IS NULL AND error IS NOT NULL))
);
CREATE INDEX workflow_pending_cart ON workflow_commands(namespace,cart_id)
    WHERE operation='checkout_cart' AND state='pending';
