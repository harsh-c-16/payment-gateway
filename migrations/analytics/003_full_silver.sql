-- Immutable envelopes retain their original hashes; normalized payloads expose typed nulls.
ALTER TABLE silver_events ADD COLUMN normalized_payload jsonb;
UPDATE silver_events SET normalized_payload=document->'payload';
ALTER TABLE silver_events ALTER COLUMN normalized_payload SET NOT NULL;

-- Versions identify one snapshot across event types within the producer's aggregate.
ALTER TABLE silver_events ADD CONSTRAINT silver_aggregate_version
    UNIQUE(namespace,source_service,aggregate_type,aggregate_id,aggregate_version);
DO $$
DECLARE legacy text;
BEGIN
    SELECT conname INTO legacy FROM pg_constraint
    WHERE conrelid='silver_events'::regclass AND contype='u'
      AND pg_get_constraintdef(oid)=
          'UNIQUE (namespace, source_service, aggregate_type, aggregate_id, aggregate_version, event_type)';
    IF legacy IS NOT NULL THEN
        EXECUTE format('ALTER TABLE silver_events DROP CONSTRAINT %I',legacy);
    END IF;
END $$;
