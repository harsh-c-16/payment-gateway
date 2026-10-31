# M01b: low-memory Kafka and Schema Registry

The real smoke/recreation check passed on the current Windows/WSL2 machine;
[progress](../docs/vichitr/progress.md) retains exact outcomes and failed attempts.

Run from the repository root with the existing Python 3.11 environment and Docker
Desktop's Linux engine. The default ports must be available. No new dependency
lock, cloud service or paid provider is needed.

```powershell
$env:PROJECTCTL_ADAPTER_MODULE = 'infra.streaming'
.venv/Scripts/python.exe -m projectctl env up --profile streaming-local
.venv/Scripts/python.exe -m projectctl env verify --profile streaming-local
```

This overlays `compose.streaming.yaml` on `compose.yaml` using the **same Compose
project and PostgreSQL volume** as M01a. PostgreSQL may be recreated to apply the
smaller allocation, without resetting data or changing passwords. Do not switch
to the PostgreSQL-only adapter during streaming work: that profile expects its
original 2-GiB PostgreSQL limit and verifies a different allocation.

| Service | RAM ceiling | CPU ceiling | Host endpoint | Compose endpoint |
|---|---:|---:|---|---|
| PostgreSQL | 512 MiB | 0.5 | 127.0.0.1:5432 | postgres:5432 |
| Kafka | 1,024 MiB | 0.75 | 127.0.0.1:9092 | kafka:9092 |
| Schema Registry | 640 MiB | 0.5 | http://127.0.0.1:8081 | http://schema-registry:8081 |

The three service limits total **2,176 MiB**. Kafka's Java heap is 256 MiB;
registry heap starts at 128 MiB and is capped at 256 MiB. These are development
settings to verify on the current Docker VM, not a claim of measured performance
or a complete integrated benchmark allocation. Profiles and evidence record the
actual limits; no 8-GiB allocation is assumed. Later comparisons must keep the same
verified controls. Jaineel coordinates the canonical evaluation configuration.

Images use immutable digests in [images.lock.json](images.lock.json), from the
[Apache Kafka 4.1 image](https://kafka.apache.org/41/getting-started/docker/) and
[Confluent Schema Registry 8.1 image configuration](https://docs.confluent.io/platform/8.1/installation/docker/config-reference.html).
Kafka is a single combined KRaft broker/controller, with separate internal and
loopback host listeners. Auto topic creation is disabled. This profile does not
prove replicated durability or disk-loss recovery.

`env up` creates the five `dev.<domain>.v1` business topics and
`dev.dead-letter.v1`: one partition, replication factor one, seven-day retention.
Existing topic partitions/retention must match; provisioning never repartitions or
silently modifies them. `provision_topics(namespace, partitions)` is the owned
adapter for future isolated test deployments; no competing CLI is introduced.

Consumer group names are declared separately for analytics and catalogue stock
projection. Kafka materializes a group when consumers join/commit; idle worker
groups are not fabricated. The live smoke test creates two real independent groups.

Schema Registry stores schema metadata in Kafka's retained `_schemas` topic.
It defaults to `BACKWARD_TRANSITIVE`. **M02 still must supply and review/register
the canonical business and DLQ schemas.** Infrastructure readiness does not claim
those contracts are ready. The smoke subject `infra-smoke.v1-value` is an explicit
infrastructure fixture, not a substitute domain schema.

Use `RUN_NAMESPACE=dev` for future local services. The shared `.env.example`
currently says `local-dev`, while common §7 specifies `dev` or isolated `bench-`/
`replay-` namespaces. Jaineel must coordinate that template correction before
service integration; this module does not silently change the shared contract.

Kafka data uses the named `kafka_data` volume. The named `lakehouse_data` volume is
also provisioned for the upcoming FileStore; no Bronze/Silver/Gold path is claimed
until M04/M05. All are local Docker-managed volumes. Service passwords remain in
the same ignored `artifacts/infra/postgres-local/` directory used by M01a.

After successful startup, run the explicit real smoke check:

```powershell
$env:RUN_STREAMING_LIVE_TESTS = '1'
.venv/Scripts/python.exe -m pytest tests/pipelines/test_streaming_live.py -q
Remove-Item Env:RUN_STREAMING_LIVE_TESTS
```

It registers/evolves a JSON Schema, rejects an incompatible change, validates and
publishes plain JSON with schema-ID headers and broker acknowledgement, reads it
through independent groups, and recreates Kafka/registry containers to check the
record, committed offset and registered schema survive. It uses fresh `bench-`
topics and retains them for evidence; it does not change dev business offsets.
Container recreation interrupts this project's broker/registry: run before starting
application work. A passing smoke does not prove the later sink disposition rules.

Offline checks remain `python -m pytest tests/pipelines -q`. The PostgreSQL-only
live test is a different profile; do not enable both live flags in one invocation.
CLI facts are in `artifacts/infra/streaming-local/checks/<run_id>/streaming.json`,
with CLI summaries in the existing `artifacts/projectctl/<run_id>/` directories.

Stop these services while retaining all volumes and credentials:

```powershell
.venv/Scripts/python.exe -m projectctl env down
```

Keep `PROJECTCTL_ADAPTER_MODULE=infra.streaming` for this command. No reset/cleanup
provider or business migration/import is implemented. The supplied CSV was checked
against the published hash/size and stays Git-ignored; Harsh still owns its import.
See [progress](../docs/vichitr/progress.md) for actual checks and limitations.
