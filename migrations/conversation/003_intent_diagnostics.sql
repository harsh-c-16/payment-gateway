-- Private per-turn model provenance/usage, committed with the response and local outbox.
-- Existing turns remain null: missing historical usage is never reconstructed as zero.
ALTER TABLE turns ADD COLUMN IF NOT EXISTS intent_diagnostic jsonb;

-- Independently committed attempt reservations survive a response/outbox transaction failure.
-- They are private M1 audit state, not a second event outbox or a purchase effect.
CREATE TABLE IF NOT EXISTS intent_attempts (
    namespace varchar(64) NOT NULL,
    request_id uuid NOT NULL,
    run_id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id varchar(128) NOT NULL,
    request_hash char(64) NOT NULL,
    provider_config jsonb NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    diagnostic jsonb,
    PRIMARY KEY (namespace, request_id)
);
