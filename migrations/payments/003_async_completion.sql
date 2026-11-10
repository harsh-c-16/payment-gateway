-- Durable simulator plan. Existing published attempts and events are untouched.
ALTER TABLE payment_attempts ADD COLUMN IF NOT EXISTS completion_due_at timestamptz;
ALTER TABLE payment_attempts ADD COLUMN IF NOT EXISTS planned_failure_code varchar(128);
ALTER TABLE payment_attempts ADD COLUMN IF NOT EXISTS origin_context jsonb;
ALTER TABLE payment_attempts ADD COLUMN IF NOT EXISTS benchmark_headers jsonb;
CREATE INDEX IF NOT EXISTS payment_completion_due
    ON payment_attempts (completion_due_at) WHERE status = 'PENDING';
