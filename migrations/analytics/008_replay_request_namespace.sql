-- API idempotency belongs to the caller's source namespace, not the new target.
-- Existing library-only bindings keep their original target-scoped identity.
ALTER TABLE replay_keys RENAME COLUMN target_namespace TO request_namespace;
