"""Frozen logical workloads. No provider cleaner, event builder or business rules."""

import hashlib
import math
import random
import re
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from benchmarks.quality import quality_expectations
from projectctl.artifacts import canonical_json
from projectctl.config import WORKLOADS, InputError


def digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class WorkloadManifest:
    """Canonical recipe bytes prevent caller mutation after fixture freezing."""

    recipe: bytes

    def as_dict(self):
        import json

        value = json.loads(self.recipe)
        return value | {"logical_fixture_sha256": hashlib.sha256(self.recipe).hexdigest()}

    def records(self):
        spec = self.as_dict()
        workload, seed = spec["workload_id"], spec["seed"]
        rng = random.Random(seed)
        skus, templates = spec["selected_skus"], spec["templates"]
        transaction = workload in {"W-CHECKOUT", "W-INTEGRATED"}
        scenario_version = spec.get("transaction_scenario_version", 1)
        if transaction and (type(scenario_version) is not int or scenario_version not in {1, 2}):
            raise InputError("unsupported transaction scenario identity version")
        ordinal = 0
        versions = {}
        if workload == "W-QUALITY":
            for expected in quality_expectations(seed):
                yield expected | {
                    "scenario_id": expected["logical_record_id"],
                    "phase": "measurement",
                    "offset_seconds": None,
                    "payload": {"invalid_subcase": expected["invalid_subcase"]},
                }
            return
        # Canonical JSON sorts object keys. Time order must be explicit.
        for phase in ("warmup", "measurement"):
            count = spec["phase_counts"].get(phase, 0)
            order = list(range(len(templates)))
            declined_positions = set()
            for index in range(count):
                if templates and index % len(templates) == 0:
                    rng.shuffle(order)
                template = templates[order[index % len(templates)]] if templates else {}
                scenario = template.get("scenario_id", template.get("query_id", f"case-{index:06}"))
                scenario_id = f"{phase}:{scenario}"
                payload = dict(template)
                if skus:
                    # Exact 80% of each block of ten hits one hot key.
                    hot = spec["key_distribution"] == "hot80" and index % 10 < 8
                    sku = skus[0] if hot else skus[index % len(skus)]
                    if workload in {"W-CHECKOUT", "W-INTEGRATED"} and "sku" in template:
                        sku = template["sku"]
                        if sku not in skus:
                            raise InputError("cart template SKU is absent from active manifest")
                    payload |= {"sku": sku, "quantity": 1}
                if transaction:
                    if scenario_version == 2:
                        # A cart template is reused by many logical purchases.
                        # Seed its ordinal in an exact 95/5 block independently
                        # of runtime identity and the template shuffle.
                        scenario_id = f"{phase}:{index:06}:{scenario}"
                        payload["scenario_id"] = scenario_id
                        if index % 100 == 0:
                            block_seed = int(
                                digest({"seed": seed, "phase": phase, "block": index // 100})[:16],
                                16,
                            )
                            declined_positions = set(
                                random.Random(block_seed).sample(range(100), 5)
                            )
                        declined = index % 100 in declined_positions
                    else:
                        # Reconstruct historical version-1 evidence exactly.
                        bucket = int(digest({"scenario": scenario, "seed": seed})[:16], 16) % 100
                        declined = bucket >= 95
                    payload |= {
                        "payment_outcome": "decline" if declined else "success",
                        "payment_delay_ms": 100,
                    }
                if workload == "W-PIPE":
                    versions[sku] = versions.get(sku, 0) + 1
                    payload |= {
                        "event_type": "STOCK_UPDATED",
                        "source_service": "benchmark",
                        "stock_version": versions[sku],
                        "on_hand": 10000,
                        "reserved": 0,
                        "available": 10000,
                        "order_id": None,
                        "reservation_id": None,
                        "reason_code": None,
                        "synthetic": True,
                        "target_event_bytes": 1024,
                    }
                offset = None
                if spec["kind"] == "sustained":
                    offset = index / spec["rate_per_second"]
                    if phase == "measurement":
                        offset += spec["warmup_seconds"]
                yield {
                    "record_ordinal": ordinal,
                    "logical_record_id": f"source-{ordinal:06}",
                    "logical_event_id": f"event-{ordinal:06}" if workload == "W-PIPE" else None,
                    "scenario_id": scenario_id,
                    "phase": phase,
                    "offset_seconds": offset,
                    "payload": payload,
                    "expected_disposition": "new_valid",
                    "duplicate_of": None,
                }
                ordinal += 1


def generate_workload(
    workload_id,
    seed,
    catalog_manifest=None,
    *,
    rate_per_second=None,
    duration_seconds=600,
    warmup_seconds=60,
    key_count=10000,
    key_distribution="uniform",
    templates=(),
    record_count=None,
    warmups_per_query=3,
    executions_per_query=30,
):
    """Select only supplied active SKUs; freeze templates before seeing responses.

    catalog_manifest is a harness projection, not a new Harsh DTO. Its reviewed
    binding supplies active_skus and provenance. Small synthetic inputs are tests.
    """
    if workload_id not in WORKLOADS or type(seed) is not int or seed < 0:
        raise InputError("known workload and nonnegative seed required")
    for value in (duration_seconds, warmup_seconds, rate_per_second or 1):
        if isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise InputError("finite nonnegative workload timing required")
    if duration_seconds <= 0 or type(key_count) is not int or key_count <= 0:
        raise InputError("positive duration and key count required")
    if key_distribution not in {"uniform", "hot80"}:
        raise InputError("unknown key distribution")
    kind = {
        "W-IMPORT": "finite",
        "W-QUALITY": "finite",
        "W-AGENT": "finite",
        "W-ANALYTICS": "queries",
    }.get(workload_id, "sustained")
    rate = (
        rate_per_second
        if rate_per_second is not None
        else {
            "W-PIPE": 500,
            "W-SEARCH": 20,
            "W-CHECKOUT": 10,
            "W-INTEGRATED": 10,
        }.get(workload_id)
    )
    if kind == "sustained" and (rate is None or rate <= 0):
        raise InputError("positive sustained offered rate required")
    selected = []
    if workload_id in {"W-PIPE", "W-QUALITY", "W-CHECKOUT", "W-INTEGRATED"}:
        active = (catalog_manifest or {}).get("active_skus", [])
        if (
            not isinstance(active, list)
            or any(
                not isinstance(s, str) or not re.fullmatch(r"[\x21-\x7e]{1,64}", s) for s in active
            )
            or len(set(active)) != len(active)
            or len(active) < (key_count if workload_id in {"W-PIPE", "W-QUALITY"} else 1)
        ):
            raise InputError("reviewed active SKU projection missing, invalid or too small")
        selected = (
            sorted(random.Random(seed).sample(sorted(active), key_count))
            if workload_id
            in {
                "W-PIPE",
                "W-QUALITY",
            }
            else sorted(active)
        )
    templates = list(templates)
    if workload_id in {"W-SEARCH", "W-INTEGRATED", "W-AGENT", "W-ANALYTICS"} and not templates:
        raise InputError("frozen query/scenario templates unavailable")
    if kind == "sustained":

        def offers(seconds):
            return int(
                (Decimal(str(seconds)) * Decimal(str(rate))).to_integral_value(
                    rounding=ROUND_CEILING
                )
            )

        counts = {"warmup": offers(warmup_seconds), "measurement": offers(duration_seconds)}
    elif kind == "queries":
        if warmups_per_query < 0 or executions_per_query <= 0:
            raise InputError("query execution counts invalid")
        counts = {
            "warmup": len(templates) * warmups_per_query,
            "measurement": len(templates) * executions_per_query,
        }
    else:
        count = {"W-IMPORT": 1, "W-QUALITY": 100000, "W-AGENT": len(templates)}[workload_id]
        if record_count is not None and workload_id == "W-AGENT" and record_count != count:
            raise InputError("scenario count differs from frozen workload")
        counts = {"measurement": count}
    spec = {
        "schema_version": 1,
        "workload_id": workload_id,
        "seed": seed,
        "kind": kind,
        "rate_per_second": rate,
        "warmup_seconds": warmup_seconds if kind == "sustained" else None,
        "duration_seconds": duration_seconds if kind == "sustained" else None,
        "key_distribution": key_distribution,
        "selected_skus": selected,
        "catalog_manifest_sha256": digest(catalog_manifest) if catalog_manifest else None,
        "templates": templates,
        "phase_counts": counts,
        "source_observations": 20000 if workload_id == "W-IMPORT" else None,
        "expected_counts": {
            "planned": sum(counts.values()),
            "unique_valid": 98500 if workload_id == "W-QUALITY" else sum(counts.values()),
            "duplicate_deliveries": 1000 if workload_id == "W-QUALITY" else 0,
            "invalid": 500 if workload_id == "W-QUALITY" else 0,
        },
    }
    if workload_id in {"W-CHECKOUT", "W-INTEGRATED"}:
        # Pin the changed materialization policy in new recipe hashes. Previously
        # saved recipes still reconstruct their original v1 evidence unchanged.
        spec["transaction_scenario_version"] = 2
    return WorkloadManifest(canonical_json(spec))
