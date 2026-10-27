import copy

import pytest

from benchmarks.metrics import (
    SLOTS,
    cohort_rates,
    group_kafka_lag,
    kafka_lag,
    latency_summary,
    nearest_rank,
    percent_change,
    ratio,
    slot_f1,
)


@pytest.mark.parametrize("q,expected", [(0.5, 30), (0.95, 100), (0.99, 100), (1, 100)])
def test_manual_nearest_rank_examples(q, expected):
    assert nearest_rank([10, 20, 30, 40, 100], q) == expected


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "10"])
def test_bad_timing_samples_rejected(bad):
    with pytest.raises(ValueError):
        nearest_rank([bad], 0.99)


def test_missing_and_unresolved_timing_is_not_zero():
    missing = latency_summary([None], expected_count=2, completed_count=1)
    assert missing["completed_only"]["p99"] is None
    assert missing["complete_cohort_p99"] is None
    assert missing["status"] == "INCOMPLETE"
    assert missing["missing_timing_count"] == 1 and missing["unresolved_count"] == 1
    assert nearest_rank([], 0.5) is None
    observed = latency_summary([10, 20, 30, 40, 100], expected_count=6)
    assert observed["completed_only"]["p99"] == 100
    assert observed["complete_cohort_p99"] is None
    assert "more than 1%" in observed["limitation"]


def test_complete_latency_cohort_preserves_sample_count():
    result = latency_summary([10, 20, 30, 40, 100], expected_count=5)
    assert result["status"] == "MEASURED" and result["sample_count"] == 5
    assert result["complete_cohort_p99"] == 100 and result["unresolved_count"] == 0
    assert latency_summary([], expected_count=0)["unresolved_percentage"] is None


def test_manual_lag_and_percentage_examples():
    assert kafka_lag(25, 20) == 5
    assert percent_change(100, 80, direction="reduction")["value"] == 20
    assert percent_change(100, 125, direction="gain")["value"] == 25
    assert percent_change(100, 110, direction="reduction")["value"] == -10
    assert percent_change(0, 100, direction="gain")["value"] is None
    assert ratio(1, 0) is None
    with pytest.raises(ValueError):
        kafka_lag(20, 25)
    assert (
        group_kafka_lag(
            [
                {"topic": "t", "partition": 0, "log_end_next": 25, "committed_next": 20},
                {"topic": "t", "partition": 1, "log_end_next": 10, "committed_next": 7},
            ]
        )
        == 8
    )
    assert group_kafka_lag([]) is None


def test_original_six_slot_f1_wrong_values_count_fp_and_fn():
    labels = [{slot: (100 if slot == "max_price_minor" else "wanted") for slot in SLOTS}]
    predictions = copy.deepcopy(labels)
    predictions[0]["size"] = "wrong"
    predictions[0]["colour"] = None
    result = slot_f1(labels, predictions)
    assert result["slots"]["size"]["fp"] == 1 and result["slots"]["size"]["fn"] == 1
    assert result["slots"]["colour"]["fn"] == 1
    assert result["macro_f1"] == pytest.approx(4 / 6)
    assert result["excluded_slots"] == []


def test_null_matches_do_not_inflate_f1_and_unlabelled_slots_are_visible():
    labels = [{slot: None for slot in SLOTS}]
    result = slot_f1(labels, labels)
    assert result["macro_f1"] is None
    assert result["excluded_slots"] == list(SLOTS)
    assert all(row["tn"] == 1 for row in result["slots"].values())
    predictions = [{**labels[0], "size": "M"}]
    result = slot_f1(labels, predictions)
    assert result["slots"]["size"]["fp"] == 1
    assert result["slots"]["size"]["exclusion_reason"]


def test_unavailable_size_label_is_not_rewritten_to_null():
    labels = [{slot: ("M" if slot == "size" else None) for slot in SLOTS}]
    predictions = [{slot: None for slot in SLOTS}]
    assert slot_f1(labels, predictions)["slots"]["size"]["fn"] == 1


def test_rates_separate_physical_admission_unique_goodput_and_drain():
    domain = "single-host-fixture"
    planned = [
        {"record_id": record, "event_id": event, "scheduled_at": at, "clock_domain": domain}
        for record, event, at in [
            ("warmup", "warmup-event", 5),
            ("r1", "e1", 11),
            ("r2", "e1", 12),
            ("r3", None, 13),
            ("r4", "e2", 17),
            ("r5", "e3", 18),
            ("after", "after-event", 20),
        ]
    ]
    admissions = [
        {"record_id": record, "status": status, "at": at, "clock_domain": domain}
        for record, status, at in [
            ("r1", "accepted", 11),
            ("r2", "accepted", 12),
            ("r3", "accepted", 13),
            ("r4", "accepted", 20.5),
            ("r5", "unknown", None),
        ]
    ]
    visible = [
        {"event_id": event, "at": at, "clock_domain": domain, "active_membership_verified": True}
        for event, at in [("warmup-event", 15), ("e1", 14), ("e1", 14), ("e2", 25)]
    ]
    result = cohort_rates(
        planned,
        admissions,
        visible,
        expected_valid_ids={"e1", "e2", "e3", "warmup-event"},
        start=10,
        end=20,
        drain_end=30,
        clock_domain=domain,
    )
    assert result["offered_per_second"] == 0.5
    assert result["admitted_per_second"] == 0.3
    assert result["gold_goodput_per_second"] == 0.1
    assert result["completion_fraction"] == pytest.approx(2 / 3)
    assert result["post_window_drain_completions"] == 1
    assert result["unknown_admissions"] == 1 and result["unresolved_count"] == 1
    assert result["status"] == "INCOMPLETE"


def test_zero_window_and_different_machine_clocks_are_explicit():
    result = cohort_rates(
        [], [], [], expected_valid_ids=set(), start=1, end=1, drain_end=1, clock_domain="host-a"
    )
    assert result["offered_per_second"] is None and result["status"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="clock"):
        cohort_rates(
            [{"record_id": "r1", "event_id": "e1", "scheduled_at": 1, "clock_domain": "host-b"}],
            [],
            [],
            expected_valid_ids={"e1"},
            start=0,
            end=2,
            drain_end=3,
            clock_domain="host-a",
        )


def test_gold_visibility_cannot_precede_first_planned_offer():
    with pytest.raises(ValueError, match="precedes"):
        cohort_rates(
            [{"record_id": "r1", "event_id": "e1", "scheduled_at": 15, "clock_domain": "host"}],
            [{"record_id": "r1", "status": "accepted", "at": 16, "clock_domain": "host"}],
            [
                {
                    "event_id": "e1",
                    "at": 11,
                    "clock_domain": "host",
                    "active_membership_verified": True,
                }
            ],
            expected_valid_ids={"e1"},
            start=10,
            end=20,
            drain_end=30,
            clock_domain="host",
        )


def test_missing_admission_receipt_cannot_be_reported_as_zero_admission():
    result = cohort_rates(
        [{"record_id": "r1", "event_id": "e1", "scheduled_at": 1, "clock_domain": "host-a"}],
        [],
        [],
        expected_valid_ids={"e1"},
        start=0,
        end=2,
        drain_end=3,
        clock_domain="host-a",
    )
    assert result["missing_admission_receipts"] == 1
    assert result["admitted_per_second"] is None and result["status"] == "INCOMPLETE"
