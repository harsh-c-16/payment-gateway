-- M09 adds processing annotations; immutable source envelopes are unchanged.
CREATE TABLE event_time_partitions (
    namespace varchar(62) NOT NULL,
    topic text NOT NULL,
    partition integer NOT NULL,
    maximum_event_time timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    PRIMARY KEY(namespace,topic,partition)
);
CREATE TABLE event_time_watermarks (
    namespace varchar(62) PRIMARY KEY,
    watermark timestamptz,
    evaluated_at timestamptz NOT NULL,
    active_partitions integer NOT NULL
);
INSERT INTO event_time_partitions
    SELECT e.namespace,e.source_topic,e.source_partition,max(e.event_time),max(s.ingested_at)
    FROM silver_events e JOIN source_receipts s ON s.namespace=e.namespace
        AND s.topic=e.source_topic AND s.partition=e.source_partition
        AND s.offset_number=e.source_offset
    GROUP BY e.namespace,e.source_topic,e.source_partition;
CREATE TABLE event_time_observations (
    namespace varchar(62) NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL,
    watermark_before timestamptz,
    timestamp_quality text[] NOT NULL,
    revision bigint NOT NULL CHECK(revision > 0),
    reason text NOT NULL CHECK(reason IN ('INGESTION','LATE_RECONCILIATION')),
    PRIMARY KEY(namespace,event_id),
    FOREIGN KEY(namespace,event_id) REFERENCES silver_events(namespace,event_id)
);
CREATE VIEW event_time_windows AS
    SELECT p.*, w.watermark,
        COALESCE(p.minute + interval '60 seconds' <= w.watermark,false)
            AS provisionally_complete
    FROM pipeline_minute p LEFT JOIN event_time_watermarks w USING(namespace);
CREATE VIEW event_time_visibility AS
    SELECT t.*, v.generation, v.observed_at, v.timing_validity,
        CASE WHEN t.reason='LATE_RECONCILIATION' THEN 'late_correction'
            ELSE 'initial_visibility' END AS latency_kind,
        extract(epoch FROM v.observed_at-s.ingested_at) AS ingress_to_visibility_seconds,
        extract(epoch FROM v.observed_at-t.processed_at) AS processing_to_visibility_seconds
    FROM event_time_observations t
    JOIN silver_events e USING(namespace,event_id)
    JOIN source_receipts s ON s.namespace=e.namespace AND s.topic=e.source_topic
        AND s.partition=e.source_partition AND s.offset_number=e.source_offset
    LEFT JOIN event_visibility v ON v.namespace=t.namespace AND v.event_id=t.event_id;
