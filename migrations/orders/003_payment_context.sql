-- Append-only upgrade: original ingress identity survives saga restarts.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS origin_context jsonb;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS benchmark_headers jsonb;
