-- Replay pins original captures/snapshots; it owns only an initially empty target.
CREATE TABLE replay_jobs (
    replay_id uuid PRIMARY KEY,
    target_namespace varchar(62) NOT NULL UNIQUE,
    request jsonb NOT NULL,
    request_sha256 char(64) NOT NULL,
    transform_version varchar(128) NOT NULL,
    code_commit varchar(128) NOT NULL,
    provider_sha256 char(64) NOT NULL,
    status text NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    clock_at timestamptz,
    counts jsonb NOT NULL DEFAULT '{}',
    reconciliation jsonb,
    error jsonb
);
CREATE TABLE replay_keys (
    target_namespace varchar(62) NOT NULL,
    idempotency_key varchar(128) NOT NULL,
    request_sha256 char(64) NOT NULL,
    replay_id uuid NOT NULL REFERENCES replay_jobs(replay_id),
    PRIMARY KEY(target_namespace,idempotency_key)
);
CREATE TABLE replay_inputs (
    replay_id uuid NOT NULL REFERENCES replay_jobs(replay_id),
    capture_id uuid NOT NULL REFERENCES bronze_captures(capture_id),
    namespace varchar(62) NOT NULL,
    topic text NOT NULL,
    partition integer NOT NULL,
    offset_number bigint NOT NULL,
    raw_locator varchar(128) NOT NULL,
    raw_sha256 char(64) NOT NULL,
    ingested_at timestamptz NOT NULL,
    PRIMARY KEY(replay_id,topic,partition,offset_number)
);
CREATE INDEX replay_inputs_capture ON replay_inputs(replay_id,capture_id);
CREATE TABLE replay_references (
    replay_id uuid NOT NULL REFERENCES replay_jobs(replay_id),
    namespace varchar(62) NOT NULL,
    dataset text NOT NULL,
    generation bigint NOT NULL,
    PRIMARY KEY(replay_id,dataset),
    FOREIGN KEY(namespace,dataset,generation)
        REFERENCES snapshot_manifests(namespace,dataset,generation)
);
