"""Resume durable queued/running jobs; failed jobs require an explicit retry request."""

from time import sleep

from pipelines.curation.db import rows
from pipelines.ingestion.runtime import pipeline_from_env

from .jobs import run_replay


def run_once(pipeline):
    with pipeline.connect() as tx:
        pending = rows(
            tx,
            """SELECT replay_id::text FROM replay_jobs
            WHERE status IN ('PENDING','RUNNING') AND transform_version=%s AND code_commit=%s
            ORDER BY started_at,replay_id LIMIT 1""",
            (pipeline.transform_version, pipeline.code_commit),
        )
    return run_replay(pipeline, pending[0]["replay_id"]) if pending else None


def main():
    pipeline = pipeline_from_env()
    while True:
        run_once(pipeline)
        sleep(0.250)


if __name__ == "__main__":
    main()
