-- Keep legacy accepted facts stable while the caller backfills the new reducers.
LOCK TABLE silver_events IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE gold_business_contributions (
    namespace varchar(62) NOT NULL, event_id uuid NOT NULL,
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE gold_partition_revisions (
    namespace varchar(62) NOT NULL, table_name text NOT NULL, cohort_date date NOT NULL,
    revision bigint NOT NULL CHECK(revision>0), transform_version varchar(128) NOT NULL,
    PRIMARY KEY(namespace,table_name,cohort_date)
);
CREATE TABLE gold_dirty_keys (
    namespace varchar(62) NOT NULL, event_id uuid NOT NULL,
    table_name text NOT NULL, cohort_date date NOT NULL,
    PRIMARY KEY(namespace,event_id,table_name,cohort_date),
    FOREIGN KEY(namespace,event_id) REFERENCES export_pending(namespace,event_id) ON DELETE CASCADE
);
CREATE TABLE order_fact (
    namespace varchar(62) NOT NULL, order_id uuid NOT NULL,
    aggregate_version bigint NOT NULL, event_id uuid NOT NULL,
    order_status text NOT NULL, total_amount_minor bigint NOT NULL,
    currency text NOT NULL, created_at timestamptz NOT NULL,
    user_id text NOT NULL, session_id uuid NOT NULL, quote_id uuid NOT NULL,
    failure_code text, reservation_id uuid, payment_id uuid,
    PRIMARY KEY(namespace,order_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE INDEX order_fact_cohort ON order_fact(namespace,created_at,currency);
CREATE TABLE order_cohorts (
    namespace varchar(62) NOT NULL, cohort_date date NOT NULL, currency text NOT NULL,
    PRIMARY KEY(namespace,cohort_date,currency)
);
CREATE TABLE payment_fact (
    namespace varchar(62) NOT NULL, payment_id uuid NOT NULL,
    aggregate_version bigint NOT NULL, event_id uuid NOT NULL, order_id uuid NOT NULL,
    attempt_number bigint NOT NULL, status text NOT NULL, amount_minor bigint NOT NULL,
    currency text NOT NULL, attempt_created_at timestamptz NOT NULL,
    failure_code text, debit_id uuid, reversal_id uuid,
    PRIMARY KEY(namespace,payment_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE INDEX payment_fact_cohort ON payment_fact(namespace,attempt_created_at,currency);
CREATE TABLE funnel_stages (
    namespace varchar(62) NOT NULL, order_id uuid NOT NULL,
    stage text NOT NULL CHECK(stage IN ('created','reserved','payment_success','inventory_committed','confirmed')),
    event_id uuid NOT NULL, PRIMARY KEY(namespace,order_id,stage),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE pending_order_joins (
    namespace varchar(62) NOT NULL, event_id uuid NOT NULL, order_id uuid NOT NULL,
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE INDEX pending_order_joins_parent ON pending_order_joins(namespace,order_id);
CREATE TABLE inventory_failure_outcomes (
    namespace varchar(62) NOT NULL, order_id uuid NOT NULL,
    reservation_request_id uuid NOT NULL, reason_code text NOT NULL,
    first_event_time timestamptz NOT NULL, event_id uuid NOT NULL,
    PRIMARY KEY(namespace,order_id,reservation_request_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE search_fact (
    namespace varchar(62) NOT NULL, search_id uuid NOT NULL,
    aggregate_version bigint NOT NULL, event_id uuid NOT NULL,
    completed_at timestamptz NOT NULL, mode text NOT NULL,
    returned_count bigint NOT NULL, duration_ms numeric NOT NULL CHECK(duration_ms>=0),
    PRIMARY KEY(namespace,search_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);

CREATE VIEW daily_conversion AS
SELECT c.namespace,c.cohort_date,c.currency,
    count(o.order_id) AS created_orders,
    count(*) FILTER(WHERE o.order_status='CONFIRMED') AS confirmed_orders,
    count(*) FILTER(WHERE o.order_status='CANCELLED') AS cancelled_orders,
    count(*) FILTER(WHERE o.order_status='PENDING') AS pending_orders,
    count(*) FILTER(WHERE o.order_status='CONFIRMED')::double precision
        / NULLIF(count(o.order_id),0) AS conversion,
    COALESCE(sum(o.total_amount_minor),0) AS created_amount_minor,
    COALESCE(sum(o.total_amount_minor) FILTER(WHERE o.order_status='CONFIRMED'),0) AS confirmed_amount_minor,
    COALESCE(sum(o.total_amount_minor) FILTER(WHERE o.order_status='CANCELLED'),0) AS cancelled_amount_minor,
    COALESCE(sum(o.total_amount_minor) FILTER(WHERE o.order_status='PENDING'),0) AS pending_amount_minor
FROM order_cohorts c LEFT JOIN order_fact o ON o.namespace=c.namespace
    AND (o.created_at AT TIME ZONE 'UTC')::date=c.cohort_date AND o.currency=c.currency
GROUP BY c.namespace,c.cohort_date,c.currency;

CREATE VIEW checkout_funnel AS
SELECT c.namespace,c.cohort_date,c.currency,
    count(DISTINCT s.order_id) FILTER(WHERE s.stage='created') AS created_orders,
    count(DISTINCT s.order_id) FILTER(WHERE s.stage='reserved') AS reserved_orders,
    count(DISTINCT s.order_id) FILTER(WHERE s.stage='payment_success') AS payment_success_orders,
    count(DISTINCT s.order_id) FILTER(WHERE s.stage='inventory_committed') AS inventory_committed_orders,
    count(DISTINCT s.order_id) FILTER(WHERE s.stage='confirmed') AS confirmed_orders
FROM order_cohorts c LEFT JOIN order_fact o ON o.namespace=c.namespace
    AND (o.created_at AT TIME ZONE 'UTC')::date=c.cohort_date AND o.currency=c.currency
LEFT JOIN funnel_stages s ON s.namespace=o.namespace AND s.order_id=o.order_id
GROUP BY c.namespace,c.cohort_date,c.currency;

CREATE VIEW payment_failures AS
SELECT namespace,(attempt_created_at AT TIME ZONE 'UTC')::date AS cohort_date,currency,
    CASE WHEN status='FAILED' THEN failure_code END AS failure_code,
    count(*) FILTER(WHERE status='FAILED') AS failed_attempts,
    count(*) FILTER(WHERE status='SUCCESS') AS successful_attempts,
    count(*) FILTER(WHERE status='REVERSED') AS reversed_attempts,
    count(*) FILTER(WHERE status='PENDING') AS pending_attempts,
    count(*) FILTER(WHERE status='CANCELLED') AS cancelled_attempts,
    COALESCE(sum(amount_minor) FILTER(WHERE status='FAILED'),0) AS failed_amount_minor,
    COALESCE(sum(amount_minor) FILTER(WHERE status='SUCCESS'),0) AS successful_amount_minor,
    COALESCE(sum(amount_minor) FILTER(WHERE status='REVERSED'),0) AS reversed_amount_minor,
    COALESCE(sum(amount_minor) FILTER(WHERE status='PENDING'),0) AS pending_amount_minor,
    COALESCE(sum(amount_minor) FILTER(WHERE status='CANCELLED'),0) AS cancelled_amount_minor
FROM payment_fact GROUP BY namespace,(attempt_created_at AT TIME ZONE 'UTC')::date,currency,
    CASE WHEN status='FAILED' THEN failure_code END;

CREATE VIEW inventory_failures AS
SELECT namespace,(first_event_time AT TIME ZONE 'UTC')::date AS cohort_date,
    reason_code,count(*) AS failed_reservations
FROM inventory_failure_outcomes
GROUP BY namespace,(first_event_time AT TIME ZONE 'UTC')::date,reason_code;

CREATE VIEW search_performance AS
SELECT namespace,(completed_at AT TIME ZONE 'UTC')::date AS cohort_date,mode,
    count(*) AS unique_searches, count(*) FILTER(WHERE returned_count=0) AS empty_results,
    sum(duration_ms)::text AS duration_sum_ms, count(*) AS duration_count,
    jsonb_agg(jsonb_build_object('event_id',event_id::text,'duration_ms',duration_ms::text)
              ORDER BY event_id) AS duration_references
FROM search_fact GROUP BY namespace,(completed_at AT TIME ZONE 'UTC')::date,mode;
