-- A05-A07: Saga operation keys, fault barriers, NOTIFY trigger.

-- Add operation_key column to saga_jobs for durable intended commands
ALTER TABLE saga_jobs ADD COLUMN IF NOT EXISTS operation_key varchar(128);

-- Allow CONFIRMED/CANCELLED/MANUAL_REVIEW as terminal planned_step values
ALTER TABLE saga_jobs DROP CONSTRAINT IF EXISTS saga_jobs_planned_step_check;
ALTER TABLE saga_jobs ADD CONSTRAINT saga_jobs_planned_step_check
    CHECK (planned_step IN (
        'RESERVE','AUTHORIZE_PAYMENT','COMMIT_STOCK',
        'CONFIRM','COMPENSATE_RELEASE','COMPENSATE_PAYMENT','CANCEL',
        'CONFIRMED','CANCELLED','MANUAL_REVIEW'
    ));

-- NOTIFY trigger: fires on order status change for SSE wake-up
CREATE OR REPLACE FUNCTION notify_order_change() RETURNS trigger AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status OR NEW.order_version IS DISTINCT FROM OLD.order_version THEN
        PERFORM pg_notify('order_events', NEW.namespace || ':' || NEW.order_id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER order_status_notify
    AFTER UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION notify_order_change();

-- Fault barrier table: controlled crash points for benchmark mode
CREATE TABLE IF NOT EXISTS fault_barriers (
    namespace       varchar(62)  NOT NULL,
    barrier_name    varchar(64)  NOT NULL,
    enabled         boolean      NOT NULL DEFAULT false,
    action          varchar(32)  NOT NULL DEFAULT 'CRASH'
        CHECK (action IN ('CRASH', 'DELAY', 'SKIP')),
    delay_ms        int          NOT NULL DEFAULT 0 CHECK (delay_ms >= 0),
    created_at      timestamptz  NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (namespace, barrier_name)
);
