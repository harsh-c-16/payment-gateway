"""Scoped Desktop observations. No Docker environment or service credentials exported."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from benchmarks.windows.evidence import command
from infra import postgres, streaming


def parse_cgroup(raw):
    sections, key = {}, None
    for line in raw.splitlines():
        if line.startswith("::"):
            key = line[2:]
            sections[key] = []
        elif key:
            sections[key].append(line)
    cpu = dict(line.split() for line in sections["cpu.stat"])
    events = dict(line.split() for line in sections["memory.events"])
    memory = int(sections["memory.current"][0])
    limit = sections["memory.max"][0]
    return {
        "cpu_seconds": int(cpu["usage_usec"]) / 1e6,
        "memory_bytes": memory,
        "memory_limit_bytes": None if limit == "max" else int(limit),
        "memory_peak_bytes": int(sections["memory.peak"][0]),
        "oom_kill_count": int(events["oom_kill"]),
    }


class Infrastructure:
    def __init__(self, namespace):
        self.namespace, self.previous = namespace, {}
        self.lock, self.cached, self.cached_at = threading.Lock(), None, 0
        self.admin = None

    def resources(self):
        ids = command(
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=com.docker.compose.project=" + postgres.PROJECT,
        ).splitlines()
        if not ids:
            raise RuntimeError("No project containers")
        template = (
            '{"id":{{json .Id}},"name":{{json (index .Config.Labels '
            '"com.docker.compose.service")}},"state":{{json .State}},'
            '"cpus":{{json .HostConfig.NanoCpus}},"limit":{{json .HostConfig.Memory}}}'
        )
        targets = [
            json.loads(line)
            for line in command(
                "docker", "inspect", "--format", template, *ids, timeout=5
            ).splitlines()
        ]

        def read(target):
            row = {
                "service": target["name"],
                "container_id": target["id"][:12],
                "status": "unavailable",
                "cpu_percent": None,
                "memory_bytes": None,
                "memory_limit_bytes": target["limit"],
                "allocated_cpus": target["cpus"] / 1e9,
                "oom_kill_count": None,
                "memory_peak_bytes": None,
            }
            if not target["state"]["Running"] or target["state"]["Paused"]:
                return row
            try:
                script = (
                    "for f in cpu.stat memory.current memory.max memory.peak memory.events; "
                    'do echo "::$f"; cat "/sys/fs/cgroup/$f" || exit 1; done'
                )
                values = parse_cgroup(
                    command("docker", "exec", target["id"], "sh", "-c", script, timeout=5)
                )
                stamp = time.perf_counter()
                old = self.previous.get(target["id"])
                if old and values["cpu_seconds"] >= old[1] and row["allocated_cpus"] > 0:
                    row["cpu_percent"] = (
                        (values["cpu_seconds"] - old[1])
                        / (stamp - old[0])
                        / row["allocated_cpus"]
                        * 100
                    )
                self.previous[target["id"]] = (stamp, values["cpu_seconds"])
                row.update(values, status="available" if old else "warming_up")
                if row["memory_limit_bytes"] != target["limit"]:
                    raise ValueError("Cgroup and Docker memory limits differ")
            except Exception:
                row.update(status="unavailable", cpu_percent=None, memory_bytes=None)
            return row

        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(read, targets))

    def lag(self):
        from confluent_kafka.admin import AdminClient

        from benchmarks.collectors import KafkaLagReader

        if self.admin is None:
            self.admin = AdminClient(
                {"bootstrap.servers": streaming.BOOTSTRAP, "socket.timeout.ms": 1500}
            )
        metadata = self.admin.list_topics(timeout=2)
        output = []
        for group, domains in (
            ("analytics", streaming.DOMAINS[:-1]),
            ("catalog-projection", ("inventory-events",)),
        ):
            targets = []
            for domain in domains:
                topic = f"{self.namespace}.{domain}.v1"
                found = metadata.topics.get(topic)
                if found is None or found.error:
                    raise RuntimeError("Topic metadata unavailable")
                targets.extend((topic, partition) for partition in sorted(found.partitions))
            reader = KafkaLagReader(self.admin, f"{self.namespace}.{group}.v1", targets)
            readings = reader.read_sync()
            for series in reader.series:
                reading = readings.get(series.key)
                labels = dict(series.labels)
                output.append(
                    {
                        **labels,
                        "lag": reading.value if reading else None,
                        "status": "available" if reading else "unavailable",
                        **(reading.details if reading else {}),
                    }
                )
        return output

    def snapshot(self):
        from benchmarks.failure_demo.runtime import now

        with self.lock:
            if self.cached and time.monotonic() - self.cached_at < 3:
                return self.cached
            result = {
                "namespace": self.namespace,
                "observed_at": now(),
                "resources": None,
                "lag": None,
                "cpu_basis": "delta cgroup CPU seconds / elapsed seconds / allocated CPUs",
                "memory_basis": "cgroup memory.current; includes page cache, not process RSS",
                "lag_basis": "broker log-end next offset minus committed next offset",
            }
            for name, read in (("resources", self.resources), ("lag", self.lag)):
                try:
                    result[name] = read()
                except Exception:
                    pass
            result["complete"] = (
                bool(result["resources"])
                and bool(result["lag"])
                and all(r["status"] == "available" for r in result["resources"] + result["lag"])
            )
            self.cached, self.cached_at = result, time.monotonic()
            return result
