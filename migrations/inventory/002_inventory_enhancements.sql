-- A06-A07: NOTIFY trigger for reservation state changes, fault barriers.

-- NOTIFY trigger for reservation state changes
CREATE OR REPLACE FUNCTION notify_reservation_change() RETURNS trigger AS $$
BEGIN
    IF NEW.state IS DISTINCT FROM OLD.state THEN
        PERFORM pg_notify('reservation_events', NEW.namespace || ':' || NEW.order_id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER reservation_state_notify
    AFTER UPDATE ON reservations
    FOR EACH ROW
    EXECUTE FUNCTION notify_reservation_change();

-- Fault barrier table for inventory service
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
