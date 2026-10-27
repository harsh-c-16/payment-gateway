"""P8 case inventory, independent invariants and frozen runbook alias expansion.

These are harness projections, not replacement service DTOs. Owners must review
their export bindings before a real case can run (docs/integration_runbook.md).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    case_id: str
    suite: str
    owner: str
    scenario: str
    checks: tuple[tuple[str, object], ...]
    reconcile: bool = True
    barrier: str | None = None
    target: str | None = None
    outage: bool = False


def _case(suite, name, owner, scenario, checks, **kwargs):
    return Case(suite + "/" + name, suite, owner, scenario, tuple(checks.items()), **kwargs)


CASES = (
    _case(
        "contracts",
        "all",
        "all owners",
        "Validate all provider contracts and examples",
        {"contracts_checked": True, "contract_failures": 0},
        reconcile=False,
    ),
    _case(
        "D-01",
        "source",
        "Harsh",
        "Profile the untouched source independently",
        {
            "source_rows": 20000,
            "columns": 15,
            "unique_observations": 20000,
            "unique_pid": 19998,
            "missing_both_prices": 78,
        },
        reconcile=False,
    ),
    _case(
        "D-02",
        "normalize",
        "Harsh",
        "Independent dirty and full-file normalization checks",
        {
            "active": 19920,
            "inactive": 78,
            "superseded": 2,
            "rejected": 0,
            "canonical": 19998,
            "unknown_categories": 323,
            "usable_sizes": 4,
            "dirty_fixture_failures": 0,
            "shuffled_digest_equal": True,
        },
        reconcile=False,
    ),
    _case(
        "D-03",
        "resume",
        "Harsh / Aditya",
        "Import twice and resume before promotion; seed twice",
        {
            "business_digest_equal": True,
            "partial_catalog_ready": False,
            "second_seed_new_effects": 0,
            "inactive_seeded_or_quoted": 0,
        },
        reconcile=False,
        barrier="after_staging_chunk_commit_before_promotion",
        target="catalog-import",
    ),
    _case(
        "smoke",
        "G1",
        "Vichitr",
        "Valid, identical duplicate and invalid wire to active Gold",
        {
            "physical_deliveries": 3,
            "bronze_records": 3,
            "silver_unique": 1,
            "quarantined": 1,
            "gold_logical_effects": 1,
        },
    ),
    *(
        _case(
            "smoke",
            "G3-" + name,
            "all owners",
            "Search, cart, quote, explicit confirmation, order, stock projection and Gold",
            {
                "terminal_status": status,
                "workflow_ordering_valid": True,
                "confirmation_bound_to_quote_cart": True,
                "projection_matches_inventory": True,
                "llm_calls": 0,
            },
        )
        for name, status in (("success", "CONFIRMED"), ("decline", "CANCELLED"))
    ),
    _case(
        "T-01",
        "ingress",
        "Vichitr",
        "Wire/schema/key contract, source receipts and stage timing",
        {"wire_contract_failures": 0, "unaccounted_offers": 0, "missing_stage_times": 0},
    ),
    _case(
        "T-03",
        "quality",
        "Vichitr",
        "Frozen 100,000 physical record cleaning fixture",
        {
            "physical_deliveries": 100000,
            "disposition_mismatches": 0,
            "conflict_cases_checked": True,
            "null_version_utc_cases_checked": True,
        },
    ),
    *(
        _case(
            "T-07",
            name,
            owner,
            scenario,
            {"duplicate_logical_effects": 0, "lost_committed_effects": 0},
            barrier=barrier,
            target=target,
        )
        for name, owner, scenario, barrier, target in (
            (
                "before-commit",
                "Aditya",
                "Crash before local commit; no partial effect",
                "before_local_commit",
                "outbox-relay",
            ),
            (
                "after-commit",
                "Aditya",
                "Crash after local commit; eventual publication",
                "after_local_commit",
                "outbox-relay",
            ),
            (
                "publish-before-mark",
                "Aditya",
                "Publish then crash before outbox mark",
                "after_publish_before_outbox_mark",
                "outbox-relay",
            ),
            (
                "sink-before-offset",
                "Vichitr",
                "Sink commit then crash before offset commit",
                "after_sink_commit_before_offset_commit",
                "analytics-consumer",
            ),
        )
    ),
    _case(
        "T-07",
        "duplicate-relay",
        "Aditya / Vichitr",
        "Repeat delivery on retained-volume restart",
        {
            "duplicate_deliveries_observed": True,
            "duplicate_logical_effects": 0,
            "retained_volume_restart": True,
        },
    ),
    _case(
        "T-08",
        "100-buyers",
        "Aditya",
        "100 concurrent distinct buyers for one unit",
        {
            "buyers": 100,
            "distinct_keys": 100,
            "concurrent_start": True,
            "successful_reservations": 1,
            "stock_conflicts": 99,
            "final_on_hand": 0,
            "final_reserved": 0,
        },
    ),
    _case(
        "T-08",
        "100-retries",
        "Aditya",
        "100 concurrent copies of one reservation key",
        {"attempts": 100, "distinct_keys": 1, "logical_holds": 1},
    ),
    _case(
        "T-08",
        "multi-item",
        "Aditya",
        "Unavailable line rolls back entire multi-SKU hold",
        {"unavailable_line_present": True, "new_holds": 0, "new_debits": 0},
    ),
    _case(
        "T-08",
        "commit-expiry",
        "Aditya",
        "Serialize commit against expiry",
        {"commit_expiry_exclusive": True},
        barrier="before_inventory_commit",
        target="inventory",
    ),
    _case(
        "T-08",
        "late-payment",
        "Aditya",
        "Successful payment after expiry is compensated",
        {"terminal_status": "CANCELLED", "net_debit_minor": 0},
        barrier="before_payment_completion",
        target="payments",
    ),
    _case(
        "T-08",
        "reserve-tombstone",
        "Aditya",
        "Delayed reserve cannot revive released order",
        {"tombstone_preserved": True, "active_holds": 0},
    ),
    _case(
        "T-08",
        "response-loss",
        "Aditya",
        "Lose payment and commit responses; retry same keys",
        {
            "payment_response_lost": True,
            "commit_response_lost": True,
            "retry_keys_unchanged": True,
            "duplicate_debits": 0,
            "duplicate_stock_effects": 0,
        },
    ),
    _case(
        "T-08",
        "stock-commit-crash",
        "Aditya",
        "Recover forward after committed stock",
        {"terminal_status": "CONFIRMED", "committed_stock_released": False},
        barrier="saga-after-stock-commit",
        target="saga",
    ),
    _case(
        "T-08",
        "compensation-restart",
        "Aditya",
        "Resume interrupted compensation",
        {"false_final_state": False, "net_debit_minor": 0},
        barrier="during_compensation",
        target="saga",
    ),
    _case(
        "T-08",
        "quiescence",
        "Aditya",
        "Late success cannot bypass payment quiescence",
        {"new_attempts_after_quiescence": 0, "net_debit_minor": 0},
    ),
    _case(
        "T-09",
        "versions",
        "Harsh / Aditya",
        "v3, v2, duplicate v3, conflicting v3",
        {
            "current_version": 3,
            "stale": 1,
            "duplicate": 1,
            "conflict": 1,
            "projection_matches_inventory": True,
        },
    ),
    _case(
        "T-09",
        "bootstrap",
        "Harsh / Aditya",
        "Unknown SKU deferred durably; restart then bootstrap",
        {
            "unknown_durable_before_ack": True,
            "bootstrap_complete": True,
            "projection_independent_of_gold": True,
            "projection_matches_inventory": True,
        },
    ),
    *(
        _case(
            suite,
            "fixed",
            "Jaineel / Harsh",
            "All 60 frozen fixed scenarios and explicit purchase controls",
            {
                "scenario_count": 60,
                "llm_calls": 0,
                "implicit_purchases": 0,
                "unexpected_task_outcomes": 0,
                "missing_stage_timings": 0,
            },
            reconcile=False,
        )
        for suite in ("T-10", "D-05")
    ),
    *(
        _case(
            "T-11",
            target,
            "Jaineel / Aditya / Vichitr",
            "W-CHECKOUT continues during separate 30-second outage at measurement second 180",
            {
                "workload": "W-CHECKOUT",
                "accepted_during_outage_positive": True,
                "unknown_final_states": 0,
                "recovery_reconciled": True,
                "finality_samples_complete": True,
                "lag_samples_complete": True,
                "outbox_samples_complete": True,
                "pending_export_samples_complete": True,
            },
            target=target,
            outage=True,
        )
        for target in ("analytics", "kafka")
    ),
    *(
        _case(
            "T-12",
            name,
            "Vichitr",
            "Publication crash and active-manifest recovery",
            {
                "unpublished_files_visible": False,
                "active_manifest_valid": True,
                "duplicate_logical_effects": 0,
            },
            barrier=barrier,
            target="gold-publisher",
        )
        for name, barrier in (
            ("before-rename", "before_file_rename"),
            ("after-file", "after_durable_file_before_manifest"),
            ("before-pointer", "before_manifest_swap"),
            ("after-pointer", "after_manifest_swap"),
        )
    ),
    _case(
        "T-12",
        "stale-compaction",
        "Harsh / Vichitr",
        "Ingestion advances while compaction candidate waits",
        {"stale_candidate_rejected": True, "new_ingestion_preserved": True},
        barrier="before_manifest_swap",
        target="compaction-publisher",
    ),
    _case(
        "T-12",
        "late-parent",
        "Vichitr",
        "Fact older than 120s; payment arrives before order-created",
        {
            "late_fact_age_seconds_gt_120": True,
            "parent_join_corrected": True,
            "late_fact_preserved": True,
        },
    ),
    _case(
        "T-12",
        "replay-twice",
        "Vichitr / Aditya",
        "Replay into an empty isolated target, then repeat in the same target",
        {
            "isolated_initially_empty_target": True,
            "second_replay_new_effects": 0,
            "logical_digests_equal": True,
            "operational_state_unchanged": True,
            "operational_write_count": 0,
            "raw_invalid_record_replayed": True,
        },
    ),
)

BY_ID = {case.case_id: case for case in CASES}
ALIASES = {
    "data": ("D-01", "D-02", "D-03"),
    "correctness": ("contracts", "data", "T-01", "T-03", "T-07", "T-08", "T-09", "T-12", "D-05"),
}


def expand_suites(suites):
    """Stable union: overlapping aliases never execute a destructive case twice."""
    result = {}

    def add(suite):
        if suite in ALIASES:
            for child in ALIASES[suite]:
                add(child)
        else:
            matches = [case for case in CASES if case.suite == suite]
            if not matches:
                # Performance IDs are valid CLI inputs, but need P9 measurement adapters.
                matches = [Case(suite, suite, "workload owner", "Performance adapter required", ())]
            result.update((case.case_id, case) for case in matches)

    for suite in suites:
        add(suite)
    return tuple(result.values())
