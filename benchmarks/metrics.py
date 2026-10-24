"""Independent evaluation math, common §14 / evaluation §5. No service imports."""

import math
from collections import Counter
from decimal import ROUND_CEILING, Decimal
from statistics import mean

SLOTS = ("category", "size", "colour", "material", "max_price_minor", "occasion")


def nonnegative(value, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a finite nonnegative number")
    if not math.isfinite(value) or value < 0 or (integer and type(value) is not int):
        raise ValueError("expected a finite nonnegative number of the declared type")
    return value


def ratio(numerator, denominator):
    nonnegative(numerator)
    nonnegative(denominator)
    return None if denominator == 0 else numerator / denominator


def nearest_rank(samples, q):
    quantile = Decimal(str(q))
    if not quantile.is_finite() or not 0 < quantile <= 1:
        raise ValueError("quantile must be in (0,1]")
    values = sorted(nonnegative(value) for value in samples)
    if not values:
        return None
    index = int((quantile * len(values)).to_integral_value(rounding=ROUND_CEILING)) - 1
    return values[index]


def latency_summary(samples, *, expected_count, completed_count=None):
    """Samples include explicit None for completed records missing their timer.

    Unfinished operations are counted separately, never inserted as zero durations.
    Completed-only quantiles are not unconditional whole-cohort SLO claims.
    """
    samples = list(samples)
    completed_count = len(samples) if completed_count is None else completed_count
    for count in (expected_count, completed_count):
        nonnegative(count, integer=True)
    if len(samples) > completed_count or completed_count > expected_count:
        raise ValueError("sample/completion counts exceed declared cohort")
    values = [nonnegative(value) for value in samples if value is not None]
    missing = completed_count - len(values)
    unresolved = expected_count - completed_count
    quantiles = {f"p{percent}": nearest_rank(values, percent / 100) for percent in (50, 95, 99)}
    return {
        "quantile_method": "nearest-rank",
        "completed_only": quantiles,
        "sample_count": len(values),
        "completed_count": completed_count,
        "cohort_count": expected_count,
        "missing_timing_count": missing,
        "unresolved_count": unresolved,
        "unresolved_percentage": None if expected_count == 0 else 100 * unresolved / expected_count,
        "complete_cohort_p99": quantiles["p99"] if not (unresolved or missing) else None,
        "status": "MEASURED" if values and not (unresolved or missing) else "INCOMPLETE",
        "timing_validity": "MISSING" if missing or not values else "VALID",
        "limitation": (
            "more than 1% unresolved; whole-cohort p99 not established"
            if expected_count and unresolved / expected_count > 0.01
            else "incomplete cohort/timings"
            if unresolved or missing or not values
            else None
        ),
    }


def kafka_lag(log_end_next, committed_next):
    for offset in (log_end_next, committed_next):
        nonnegative(offset, integer=True)
    if committed_next > log_end_next:
        raise ValueError("inconsistent next-offset sample: committed exceeds log end")
    return log_end_next - committed_next


def group_kafka_lag(partitions):
    seen, total = set(), 0
    for row in partitions:
        key = (row["topic"], row["partition"])
        if key in seen:
            raise ValueError("duplicate partition lag sample")
        seen.add(key)
        total += kafka_lag(row["log_end_next"], row["committed_next"])
    return total if seen else None


def percent_change(baseline, candidate, *, direction):
    nonnegative(baseline)
    nonnegative(candidate)
    if direction not in {"reduction", "gain"}:
        raise ValueError("declare reduction or gain")
    value = None if baseline == 0 else 100 * (candidate - baseline) / baseline
    return {
        "value": -value if direction == "reduction" and value is not None else value,
        "unit": "percent",
        "direction": direction,
        "status": "INCOMPLETE" if value is None else "MEASURED",
    }


def cohort_rates(
    planned, admissions, visibility, *, expected_valid_ids, start, end, drain_end, clock_domain
):
    """Input is a harness projection, using one declared clock domain.

    Planned records are physical offers (duplicates/invalid included); Gold counts
    unique valid IDs. Visibility must come from reconciled active-file evidence.
    The measurement window is [start,end), and drain completion includes drain_end.
    """
    for value in (start, end, drain_end):
        nonnegative(value)
    if end < start or drain_end < end or not clock_domain:
        raise ValueError("invalid declared window/clock domain")
    planned, admissions, visibility = list(planned), list(admissions), list(visibility)
    for record in [*planned, *admissions, *visibility]:
        if record["clock_domain"] != clock_domain:
            raise ValueError("cannot subtract times from different clock domains")
    if len({row["record_id"] for row in planned}) != len(planned):
        raise ValueError("planned record identities must be unique")
    if len({row["record_id"] for row in admissions}) != len(admissions):
        raise ValueError("duplicate admission receipt")
    all_planned = {row["record_id"]: row for row in planned}
    cohort = {
        row["record_id"]: row for row in planned if start <= nonnegative(row["scheduled_at"]) < end
    }
    valid = {row["event_id"] for row in cohort.values()} & set(expected_valid_ids)
    admitted = unknown = 0
    for row in admissions:
        if row["record_id"] not in all_planned:
            raise ValueError("admission has no planned source record")
        if row["status"] not in {"accepted", "rejected", "unknown", "not_sent"}:
            raise ValueError("unknown admission status")
        if row["record_id"] in cohort:
            unknown += row["status"] == "unknown"
            if row["status"] == "accepted":
                if row["at"] < cohort[row["record_id"]]["scheduled_at"]:
                    raise ValueError("admission precedes its planned source record")
                admitted += start <= nonnegative(row["at"]) < end
    missing_admissions = len(cohort.keys() - {row["record_id"] for row in admissions})
    visible = {}
    for row in visibility:
        if row["active_membership_verified"] is not True:
            raise ValueError("receipt alone cannot prove active Gold visibility")
        when = nonnegative(row["at"])
        if row["event_id"] in valid:
            visible[row["event_id"]] = min(when, visible.get(row["event_id"], when))
    by_drain = {event_id for event_id, when in visible.items() if start <= when <= drain_end}
    in_window = {event_id for event_id, when in visible.items() if start <= when < end}
    seconds = end - start
    return {
        "cohort": "measurement",
        "clock_domain": clock_domain,
        "window_seconds": seconds,
        "offered_count": len(cohort),
        "admitted_count": admitted,
        "gold_goodput_count": len(in_window),
        "unknown_admissions": unknown,
        "missing_admission_receipts": missing_admissions,
        "offered_per_second": ratio(len(cohort), seconds),
        "admitted_per_second": None if missing_admissions else ratio(admitted, seconds),
        "gold_goodput_per_second": ratio(len(in_window), seconds),
        "completion_fraction": ratio(len(by_drain), len(valid)),
        "post_window_drain_completions": len(by_drain - in_window),
        "unresolved_count": len(valid - by_drain),
        "unresolved_ids": sorted(valid - by_drain),
        "status": "MEASURED"
        if seconds
        and cohort
        and valid
        and not (unknown or missing_admissions)
        and valid <= by_drain
        else "INCOMPLETE",
    }


def slot_f1(expected, observed):
    """Wrong non-null value contributes both FP and FN; true null contributes TN."""
    if len(expected) != len(observed):
        raise ValueError("labels and predictions must have equal scenario counts")
    counts = {slot: Counter(tp=0, fp=0, fn=0, tn=0) for slot in SLOTS}
    for labels, prediction in zip(expected, observed, strict=True):
        if not set(SLOTS) <= labels.keys() or set(prediction) - {
            *SLOTS,
            "brand",
            "category_path_prefix",
        }:
            raise ValueError("original six labels required; extensions must be reported separately")
        for slot in SLOTS:
            wanted, actual = labels[slot], prediction.get(slot)
            for value in (wanted, actual):
                if value is not None:
                    if slot == "max_price_minor":
                        nonnegative(value, integer=True)
                        if value > 2**63 - 1:
                            raise ValueError("intent price must fit int64")
                    elif not isinstance(value, str) or not value:
                        raise ValueError("slot values must be nonempty strings or null")
            if wanted is None and actual is None:
                counts[slot]["tn"] += 1
            elif wanted is not None and actual == wanted:
                counts[slot]["tp"] += 1
            else:
                counts[slot]["fp"] += actual is not None
                counts[slot]["fn"] += wanted is not None
    result, excluded = {}, []
    for slot, count in counts.items():
        positives = count["tp"] + count["fn"]
        denominator = 2 * count["tp"] + count["fp"] + count["fn"]
        f1 = 2 * count["tp"] / denominator if denominator else None
        reason = None if positives else "no positive labels; excluded from macro F1"
        if reason:
            excluded.append(slot)
        result[slot] = {**count, "positive_labels": positives, "f1": f1, "exclusion_reason": reason}
    included = [result[slot]["f1"] for slot in SLOTS if slot not in excluded]
    return {
        "slots": result,
        "macro_f1": mean(included) if included else None,
        "excluded_slots": excluded,
        "optional_extensions": "reported separately; not included",
    }
