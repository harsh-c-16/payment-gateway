-- M05: CONVERSATION_TURN slice. Shared outbox remains Aditya's migration.
CREATE TABLE silver_events (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    content_hash char(64) NOT NULL,
    event_time timestamptz NOT NULL,
    event_type text NOT NULL,
    source_service text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_version bigint NOT NULL,
    document jsonb NOT NULL,
    source_topic text NOT NULL,
    source_partition integer NOT NULL,
    source_offset bigint NOT NULL,
    raw_locator varchar(128) NOT NULL,
    PRIMARY KEY (namespace,event_id),
    UNIQUE(namespace,source_service,aggregate_type,aggregate_id,aggregate_version,event_type),
    FOREIGN KEY(namespace,source_topic,source_partition,source_offset)
        REFERENCES source_receipts(namespace,topic,partition,offset_number)
);
CREATE TABLE reducer_contributions (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE pipeline_minute (
    namespace varchar(62) NOT NULL,
    minute timestamptz NOT NULL,
    event_type text NOT NULL,
    source_service text NOT NULL,
    unique_events bigint NOT NULL CHECK(unique_events > 0),
    revision bigint NOT NULL CHECK(revision > 0),
    transform_version varchar(128) NOT NULL,
    PRIMARY KEY(namespace,minute,event_type,source_service)
);
CREATE TABLE export_pending (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE snapshot_manifests (
    namespace varchar(62) NOT NULL,
    dataset text NOT NULL CHECK(dataset IN ('silver','gold')),
    generation bigint NOT NULL CHECK(generation > 0),
    manifest jsonb NOT NULL,
    PRIMARY KEY(namespace,dataset,generation)
);
CREATE TABLE active_datasets (
    namespace varchar(62) NOT NULL,
    dataset text NOT NULL,
    generation bigint NOT NULL,
    PRIMARY KEY(namespace,dataset),
    FOREIGN KEY(namespace,dataset,generation)
        REFERENCES snapshot_manifests(namespace,dataset,generation)
);
CREATE TABLE manifest_members (
    namespace varchar(62) NOT NULL,
    dataset text NOT NULL,
    generation bigint NOT NULL,
    event_id uuid NOT NULL,
    PRIMARY KEY(namespace,dataset,generation,event_id),
    FOREIGN KEY(namespace,dataset,generation)
        REFERENCES snapshot_manifests(namespace,dataset,generation),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE event_visibility (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    generation bigint NOT NULL,
    observed_at timestamptz,
    timing_validity text NOT NULL DEFAULT 'missing'
        CHECK(timing_validity IN ('observed','missing','recovery_upper_bound')),
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE TABLE observation_jobs (
    namespace varchar(62) NOT NULL,
    job_id uuid NOT NULL,
    kind text NOT NULL CHECK(kind IN ('sink','gold')),
    members jsonb NOT NULL,
    observed_at timestamptz,
    PRIMARY KEY(namespace,job_id)
);
CREATE TABLE receipt_journal (
    cursor_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    topic text NOT NULL,
    partition integer NOT NULL,
    offset_number bigint NOT NULL,
    FOREIGN KEY(namespace,topic,partition,offset_number)
        REFERENCES source_receipts(namespace,topic,partition,offset_number)
);
CREATE INDEX receipt_journal_namespace_cursor ON receipt_journal(namespace,cursor_id);
ALTER TABLE quarantine ADD COLUMN quarantine_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE;
