"""Read-only independent checks for the exact file08 source, not an importer.

No archive, normalized catalogue, SKU manifest, DB writes, facet completion or
production normalizer is implemented here. Optional facet coverage awaits M2.
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCE_SHA256 = "56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1"
HEADER = (
    "uniq_id",
    "crawl_timestamp",
    "product_url",
    "product_name",
    "product_category_tree",
    "pid",
    "retail_price",
    "discounted_price",
    "image",
    "is_FK_Advantage_product",
    "description",
    "product_rating",
    "overall_rating",
    "brand",
    "product_specifications",
)
ROOTS = """Automation & Robotics; Automotive; Baby Care; Bags, Wallets & Belts;
Beauty and Personal Care; Cameras & Accessories; Clothing; Computers; Eyewear;
Food & Nutrition; Footwear; Furniture; Gaming; Health & Personal Care Appliances;
Home & Kitchen; Home Decor & Festive Needs; Home Entertainment; Home Furnishing;
Home Improvement; Household Supplies; Jewellery; Kitchen & Dining; Mobiles & Accessories;
Pens & Stationery; Pet Supplies; Sports & Fitness; Sunglasses; Tools & Hardware;
Toys & School Supplies; Watches; Wearable Smart Devices; eBooks"""
APPROVED_ROOTS = {" ".join(value.split()) for value in ROOTS.split(";")}
EXPECTED = {
    "raw_rows": 20000,
    "columns": 15,
    "unique_observations": 20000,
    "canonical_rows": 19998,
    "canonical_active": 19920,
    "canonical_inactive_missing_price": 78,
    "superseded": 2,
    "rejected_mandatory": 0,
    "unknown_category": 323,
    "missing_discounted_price": 78,
    "missing_retail_price": 78,
}
EXPECTED_SELECTED = {
    "JEAEGE8Q8GXYFTGU": {
        "row_number": 3189,
        "uniq_id": "f4e20863651ea54537388f1cd77a8776",
        "superseded_rows": [9420],
    },
    "ACCEJ6TESY7AFT5W": {
        "row_number": 7770,
        "uniq_id": "82f424a90d630acc188fcf267160a1fe",
        "superseded_rows": [7723],
    },
}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def price_minor(text):
    """Independent Decimal arithmetic for source assertions, not a load API."""
    if not text.strip():
        return None
    try:
        amount = Decimal(text)
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise ValueError("invalid source price")
        minor = amount * 100
        if minor != minor.to_integral_value() or not 1 <= minor <= 1_000_000_000:
            raise ValueError("source price outside common bounds")
        return int(minor)
    except InvalidOperation as error:
        raise ValueError("invalid source price") from error


def inspect_source(path: Path):
    report = {
        "source_path": str(path),
        "rules_version": "flipkart-v1",
        "expected_sha256": SOURCE_SHA256,
        "source_sha256": None,
        "status": "NOT_RUN",
        "observed": None,
        "expected": EXPECTED,
        "assertions": [],
        "selected_duplicates": None,
        "provider_normalization_comparison": "NOT_RUN",
        "facet_coverage_verification": "NOT_RUN",
        "performance": "NOT_RUN",
    }
    if not path.is_file():
        report["reason"] = "source CSV unavailable; no exact-count assertion executed"
        return report
    digest = sha256_file(path)
    report["source_sha256"] = digest
    if digest != SOURCE_SHA256:
        report.update(
            status="INCOMPLETE", reason="checksum mismatch; exact-count assertions not executed"
        )
        return report
    groups, observation_ids = defaultdict(list), set()
    counts = Counter()
    issues = []
    previous_limit = csv.field_size_limit(64 * 1024)
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = tuple(next(reader))
            if header != HEADER:
                raise ValueError("source CSV header differs from frozen 15-column header")
            counts["columns"] = len(header)
            for number, cells in enumerate(reader, 1):
                if len(cells) != len(HEADER):
                    raise ValueError(f"CSV width mismatch at logical record {number}")
                if (
                    any(len(cell.encode("utf-8")) > 16 * 1024 for cell in cells)
                    or sum(len(cell.encode("utf-8")) for cell in cells) > 64 * 1024
                ):
                    raise ValueError(f"source bound exceeded at logical record {number}")
                row = dict(zip(header, cells, strict=True))
                counts["raw_rows"] += 1
                observation_ids.add(row["uniq_id"])
                counts["missing_discounted_price"] += not row["discounted_price"].strip()
                counts["missing_retail_price"] += not row["retail_price"].strip()
                if (
                    not row["uniq_id"]
                    or not re.fullmatch(r"[!-~]{1,61}", row["pid"])
                    or not row["product_name"].strip()
                ):
                    counts["rejected_mandatory"] += 1
                    continue
                try:
                    timestamp = datetime.fromisoformat(
                        row["crawl_timestamp"].replace("Z", "+00:00")
                    )
                    if timestamp.tzinfo is None:
                        raise ValueError("missing source timezone")
                    timestamp = timestamp.astimezone(UTC)
                    sale = price_minor(row["discounted_price"])
                    price_minor(row["retail_price"])
                except ValueError:
                    counts["rejected_mandatory"] += 1
                    continue
                path_value = json.loads(row["product_category_tree"])
                if not isinstance(path_value, list) or len(path_value) != 1:
                    raise ValueError(f"unexpected source category shape at record {number}")
                root = path_value[0].split(">>")[0].strip()
                groups[row["pid"]].append((timestamp, row["uniq_id"], number, sale, root))
    except (OSError, UnicodeError, ValueError, csv.Error, StopIteration) as error:
        report.update(status="FAIL", reason=str(error), observed=dict(counts))
        return report
    finally:
        csv.field_size_limit(previous_limit)
    selected_duplicates = {}
    for pid, observations in groups.items():
        newest = max(observations)
        if len({item[0] for item in observations}) != len(observations):
            # Exact upload has no ties. Do not guess normalized business equivalence.
            issues.append("unexpected tied source times; mandatory identity review required")
        counts["canonical_rows"] += 1
        counts[
            "canonical_active" if newest[3] is not None else "canonical_inactive_missing_price"
        ] += 1
        counts["unknown_category"] += newest[4] not in APPROVED_ROOTS
        counts["superseded"] += len(observations) - 1
        if len(observations) > 1:
            selected_duplicates[pid] = {
                "row_number": newest[2],
                "uniq_id": newest[1],
                "superseded_rows": sorted(item[2] for item in observations if item is not newest),
            }
    counts["unique_observations"] = len(observation_ids)
    observed = {key: counts[key] for key in EXPECTED}
    assertions = [
        {
            "name": name,
            "expected": wanted,
            "observed": observed[name],
            "passed": observed[name] == wanted,
        }
        for name, wanted in EXPECTED.items()
    ]
    assertions.append(
        {
            "name": "selected_duplicate_source_ids",
            "expected": EXPECTED_SELECTED,
            "observed": selected_duplicates,
            "passed": selected_duplicates == EXPECTED_SELECTED,
        }
    )
    conserved = counts["raw_rows"] == sum(
        counts[key]
        for key in (
            "canonical_active",
            "canonical_inactive_missing_price",
            "superseded",
            "rejected_mandatory",
        )
    )
    assertions.append(
        {
            "name": "exclusive_source_disposition_conservation",
            "expected": True,
            "observed": conserved,
            "passed": conserved,
        }
    )
    report.update(
        status="PASS" if not issues and all(item["passed"] for item in assertions) else "FAIL",
        observed=observed,
        assertions=assertions,
        selected_duplicates=selected_duplicates,
        issues=issues,
    )
    return report
