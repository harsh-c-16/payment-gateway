-- Transaction membership survives a lost post-COMMIT timer observation.
CREATE TABLE sink_batches (
    batch_sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    run_id varchar(128) NOT NULL,
    capture_id uuid NOT NULL REFERENCES bronze_captures(capture_id),
    replay_id uuid,
    code_commit varchar(128) NOT NULL,
    transform_version varchar(128) NOT NULL,
    sources jsonb NOT NULL CHECK (jsonb_typeof(sources) = 'array'),
    batch_rows integer NOT NULL CHECK (batch_rows > 0),
    new_valid integer NOT NULL CHECK (new_valid >= 0),
    duplicate_delivery integer NOT NULL CHECK (duplicate_delivery >= 0),
    invalid integer NOT NULL CHECK (invalid >= 0),
    redelivery_noop integer NOT NULL CHECK (redelivery_noop >= 0),
    started_at timestamptz NOT NULL,
    committed_observed_at timestamptz,
    flush_duration_seconds double precision,
    CHECK (jsonb_array_length(sources) = batch_rows),
    CHECK (new_valid + duplicate_delivery + invalid + redelivery_noop = batch_rows),
    CHECK ((committed_observed_at IS NULL) = (flush_duration_seconds IS NULL)),
    CHECK (flush_duration_seconds >= 0 AND flush_duration_seconds < 'Infinity'::double precision)
);
CREATE INDEX sink_batches_run_cursor ON sink_batches(namespace, run_id, batch_sequence);
