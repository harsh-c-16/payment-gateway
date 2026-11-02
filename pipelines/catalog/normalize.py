"""Deterministic source rules from file 08. Pure: no database, network or model calls."""

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from shared.event_transport.schemas import canonical_json

RULES_VERSION = "flipkart-v1"
DICTIONARY_PATH = (
    Path(__file__).resolve().parents[2] / "contracts/dictionaries/catalog/flipkart-v1.json"
)
ACTIVE, INACTIVE = "canonical_active", "canonical_inactive_missing_price"
SUPERSEDED, REJECTED = "superseded", "rejected_mandatory"
CSV_FIELD_LIMIT = 1024 * 1024
BUSINESS_FIELDS = (
    "sku",
    "product_id",
    "title",
    "description",
    "category",
    "category_path_normalized",
    "brand",
    "brand_normalized",
    "size",
    "size_kind",
    "colour",
    "material",
    "seller_id",
    "price_minor",
    "retail_price_minor",
    "currency",
    "currency_source",
    "rating",
    "is_fk_advantage",
    "image_urls",
    "attributes",
    "unkeyed_specifications",
    "active",
    "inactive_reason",
)


class CsvStructureError(ValueError):
    """The file cannot be read as the frozen 15-column CSV, so nothing may be promoted."""


class SpecParseError(ValueError):
    pass


def load_dictionary(path=DICTIONARY_PATH):
    # Text mode normalizes CRLF checkouts, so Windows and Linux hash the same dictionary.
    text = Path(path).read_text(encoding="utf-8")
    document = json.loads(text)
    document["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document["root_ids"] = {label: root_slug(label) for label in document["roots"]}
    return document


def root_slug(label):
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def dataset_revision(source_sha256, rules_version, dictionary_sha256):
    material = f"{source_sha256}\n{rules_version}\n{dictionary_sha256}".encode()
    return "flipkart-v1-" + hashlib.sha256(material).hexdigest()[:24]


def clean_text(value):
    return " ".join(unicodedata.normalize("NFC", value).split())


def parse_money(text, bound):
    """Exact Decimal-to-minor-unit conversion. Returns (minor or None, invalid flag)."""
    text = text.strip()
    if not text:
        return None, False
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, True
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        return None, True
    minor = amount * 100
    if not 1 <= minor <= bound:
        return None, True
    return int(minor), False


def ruby_to_json(text):
    """Replace `=>` and bare `nil` outside quoted strings; quoted content stays untouched."""
    out, position, length = [], 0, len(text)
    while position < length:
        char = text[position]
        if char == '"':
            start = position
            position += 1
            while position < length and text[position] != '"':
                position += 2 if text[position] == "\\" else 1
            if position >= length:
                raise SpecParseError("unterminated string")
            position += 1
            out.append(text[start:position])
        elif text.startswith("=>", position):
            out.append(":")
            position += 2
        elif (
            text.startswith("nil", position)
            and (position == 0 or not text[position - 1].isalnum())
            and (position + 3 == length or not text[position + 3].isalnum())
        ):
            out.append("null")
            position += 3
        else:
            out.append(char)
            position += 1
    return "".join(out)


def _depth(value, level=1):
    children = (
        value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    )
    return max((_depth(child, level + 1) for child in children), default=level)


def parse_specifications(cell, bounds):
    """Returns (ordered entries, issue codes). Failure stays attribute-level, never row-level."""
    if not cell.strip():
        return [], ["SPEC_EMPTY"]
    try:
        document = json.loads(
            ruby_to_json(cell), parse_constant=lambda _: (_ for _ in ()).throw(SpecParseError())
        )
        if not isinstance(document, dict) or set(document) != {"product_specification"}:
            raise SpecParseError("unsupported top level")
        if _depth(document) > bounds["spec_nesting"]:
            raise SpecParseError("nesting bound")
    except (ValueError, RecursionError):
        return [], ["SPEC_PARSE_ERROR"]
    body = document["product_specification"]
    if body is None:
        return [], ["SPEC_NIL"]
    if isinstance(body, dict):
        body = [body]
    if not isinstance(body, list) or len(body) > bounds["spec_entries"]:
        return [], ["SPEC_PARSE_ERROR"]
    entries, issues = [], []
    for item in body:
        key, value = (
            (item.get("key"), item.get("value")) if isinstance(item, dict) else (None, None)
        )
        if (
            not isinstance(item, dict)
            or set(item) - {"key", "value"}
            or not isinstance(key, (str, type(None)))
            or not isinstance(value, (str, type(None)))
        ):
            issues.append("SPEC_PARSE_ERROR")
        elif key is None and value is None:
            issues.append("SPEC_PARSE_ERROR")
        else:
            entries.append({"key": key, "value": value})
            if key is None:
                issues.append("SPEC_UNKEYED")
            elif value is None:
                issues.append("SPEC_VALUE_MISSING")
    return entries, issues


def attributes_from(entries):
    attributes, unkeyed = defaultdict(list), []
    for entry in entries:
        if entry["key"] is None:
            unkeyed.append(entry["value"])
        elif entry["value"] is not None:
            attributes[clean_text(entry["key"]).casefold()].append(entry["value"])
    return dict(attributes), unkeyed


def single_value(attributes, keys):
    """First present key must hold exactly one distinct value. Returns (value, conflict)."""
    for key in keys:
        distinct = {clean_text(value).casefold() for value in attributes.get(key, ())} - {""}
        if distinct:
            return (distinct.pop(), False) if len(distinct) == 1 else (None, True)
    return None, False


def apparel_size(attributes, dictionary):
    value, conflict = single_value(attributes, [dictionary["size_key"]])
    if value is None:
        return None, conflict
    wrapped = re.fullmatch(dictionary["size_wrapper_regex"], value)
    return dictionary["size_aliases"].get(wrapped.group(1) if wrapped else value), False


def parse_category(cell, dictionary):
    """Returns (root slug or None, path segments). Unknown roots keep their raw path."""
    try:
        values = json.loads(cell)
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
            return None, []
    except ValueError:
        return None, []
    path = [clean_text(part) for part in values[0].split(">>")]
    path = [part for part in path if part]
    return (dictionary["root_ids"].get(path[0]) if path else None), path


def parse_images(cell):
    """Returns (URLs, malformed flag). Blank is an empty list; nothing is downloaded."""
    if not cell.strip():
        return [], False
    try:
        values = json.loads(cell)
    except ValueError:
        return [], True
    if not isinstance(values, list):
        return [], True
    return [
        v for v in values if isinstance(v, str) and v.startswith(("http://", "https://"))
    ], False


def parse_rating(product, overall, sentinel):
    """Returns (canonical decimal text or None, issue codes)."""
    issues, values = [], []
    for text in (product.strip(), overall.strip()):
        if not text or text == sentinel:
            values.append(None)
            continue
        try:
            value = Decimal(text)
            if not value.is_finite() or not 1 <= value <= 5:
                raise InvalidOperation
            values.append(format(value.normalize(), "f"))
        except InvalidOperation:
            issues.append("INVALID_RATING")
            values.append(None)
    if values[0] != values[1]:
        issues.append("RATING_DISAGREEMENT")
    return values[0] if values[0] is not None else values[1], issues


def parse_time(text):
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("crawl time lacks a timezone")
    return moment.astimezone(UTC)


@dataclass
class Observation:
    row_number: int
    uniq_id: str
    pid: str
    crawled_at: datetime | None
    mandatory_valid: bool
    fields: dict
    issues: list[str]
    bound_exceeded: bool = False
    business_hash: str | None = None


@dataclass
class Selection:
    canonical: list[Observation] = field(default_factory=list)
    dispositions: dict[int, str] = field(default_factory=dict)
    conflict_rows: set[int] = field(default_factory=set)
    digest: str = ""


def normalize_catalog_row(raw, row_number, dictionary):
    """One source record to one observation; a soft issue never drops the row."""
    bounds, issues = dictionary["bounds"], []
    uniq_id, pid = raw["uniq_id"].strip(), raw["pid"].strip()
    sizes = [len(value.encode("utf-8")) for value in raw.values()]
    title = clean_text(raw["product_name"])
    try:
        crawled_at = parse_time(raw["crawl_timestamp"])
    except ValueError:
        crawled_at = None
    bound_exceeded = max(sizes) > bounds["cell_bytes"] or sum(sizes) > bounds["record_bytes"]
    if bound_exceeded:
        issues.append("INPUT_BOUND_EXCEEDED")
    valid = bool(
        not bound_exceeded
        and re.fullmatch(r"[!-~]{1,128}", uniq_id)
        and re.fullmatch(r"[!-~]{1,61}", pid)
        and title
        and crawled_at
    )
    if not valid:
        return Observation(
            row_number, uniq_id, pid, crawled_at, False, {}, issues, bound_exceeded=bound_exceeded
        )
    price, bad_price = parse_money(raw["discounted_price"], bounds["price_minor_max"])
    retail, bad_retail = parse_money(raw["retail_price"], bounds["price_minor_max"])
    if bad_price or bad_retail:
        issues.append("INVALID_PRICE")
    if price is None:
        issues.append("MISSING_PRICE")
    elif retail is not None and price > retail:
        issues.append("PRICE_INCONSISTENT")
    category, path = parse_category(raw["product_category_tree"], dictionary)
    if category is None:
        issues.append("CATEGORY_UNCLASSIFIED")
    images, bad_images = parse_images(raw["image"])
    if bad_images:
        issues.append("IMAGE_PARSE_ERROR")
    flag = raw["is_FK_Advantage_product"].strip()
    if flag not in {"true", "false"}:
        issues.append("INVALID_BOOLEAN")
    description, brand = clean_text(raw["description"]) or None, clean_text(raw["brand"]) or None
    if description is None:
        issues.append("MISSING_DESCRIPTION")
    if brand is None:
        issues.append("MISSING_BRAND")
    rating, rating_issues = parse_rating(
        raw["product_rating"], raw["overall_rating"], dictionary["rating_sentinel"]
    )
    issues += rating_issues
    entries, spec_issues = parse_specifications(raw["product_specifications"], bounds)
    issues += spec_issues
    attributes, unkeyed = attributes_from(entries)
    colour, colour_conflict = single_value(attributes, dictionary["colour_keys"])
    if colour == "gray":
        colour = "grey"
    material_keys = dictionary["material_keys"]
    material, material_conflict = single_value(
        attributes, material_keys.get(category, material_keys["default"])
    )
    size, size_conflict = (
        apparel_size(attributes, dictionary)
        if category == dictionary["size_root"]
        else (None, False)
    )
    if colour_conflict or material_conflict or size_conflict:
        issues.append("ATTRIBUTE_CONFLICT")
    sku = "FK-" + pid
    fields = {
        "sku": sku,
        "product_id": sku,
        "title": title,
        "description": description,
        "category": category,
        "category_path_normalized": path,
        "category_path_raw": raw["product_category_tree"],
        "brand": brand,
        "brand_normalized": brand.casefold() if brand else None,
        "size": size,
        "size_kind": dictionary["size_kind"] if size else None,
        "colour": colour,
        "material": material,
        "seller_id": None,
        "price_minor": price,
        "retail_price_minor": retail,
        "currency": "INR",
        "currency_source": "project_assumption",
        "rating": rating,
        "is_fk_advantage": {"true": True, "false": False}.get(flag),
        "image_urls": images,
        "attributes": attributes,
        "unkeyed_specifications": unkeyed,
        "specification_entries": entries,
        "active": price is not None,
        "inactive_reason": None if price is not None else "MISSING_PRICE",
        "source_url": raw["product_url"],
        "source_pid": pid,
        "source_observation_id": uniq_id,
        "source_crawled_at": crawled_at,
        "source_row_number": row_number,
    }
    observation = Observation(row_number, uniq_id, pid, crawled_at, True, fields, issues)
    observation.business_hash = business_hash(fields)
    return observation


def business_hash(fields):
    document = {name: fields[name] for name in BUSINESS_FIELDS}
    return hashlib.sha256(canonical_json(document)).hexdigest()


def business_digest(pairs):
    return hashlib.sha256(canonical_json(sorted(pairs))).hexdigest()


def select_latest_listings(observations):
    """Latest crawl per pid; every source row gets exactly one disposition."""
    selection, groups = Selection(), defaultdict(list)
    for observation in observations:
        if observation.mandatory_valid:
            groups[observation.pid].append(observation)
        else:
            selection.dispositions[observation.row_number] = REJECTED
    for group in groups.values():
        latest = max(item.crawled_at for item in group)
        tied = [item for item in group if item.crawled_at == latest]
        if len({item.business_hash for item in tied}) > 1:
            for item in tied:
                selection.dispositions[item.row_number] = REJECTED
                selection.conflict_rows.add(item.row_number)
                item.issues.append("SOURCE_ID_CONFLICT")
            winner = None
        else:
            winner = max(tied, key=lambda item: item.uniq_id)
            selection.canonical.append(winner)
            selection.dispositions[winner.row_number] = (
                ACTIVE if winner.fields["active"] else INACTIVE
            )
        for item in group:
            if item is not winner and item.row_number not in selection.conflict_rows:
                selection.dispositions[item.row_number] = SUPERSEDED
    selection.canonical.sort(key=lambda item: item.fields["sku"])
    selection.digest = business_digest(
        [[item.fields["sku"], item.business_hash] for item in selection.canonical]
    )
    return selection


def read_source(path, dictionary):
    """Yields (row_number, raw row). 1-based logical records, never physical lines."""
    previous = csv.field_size_limit(CSV_FIELD_LIMIT)
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header != dictionary["source_header"]:
                raise CsvStructureError("CSV_STRUCTURE_ERROR: header differs from frozen header")
            for number, cells in enumerate(reader, 1):
                if len(cells) != len(header):
                    raise CsvStructureError(f"CSV_STRUCTURE_ERROR: width at record {number}")
                yield number, dict(zip(header, cells, strict=True))
    except (csv.Error, UnicodeError) as error:
        raise CsvStructureError(f"CSV_STRUCTURE_ERROR: {type(error).__name__}") from error
    finally:
        csv.field_size_limit(previous)


def profile_catalog(rows, selection, observations, source_sha256):
    """Full-file observations for profile.json; reads nothing beyond the supplied rows."""
    columns = defaultdict(Counter)
    shapes, identities, issue_counts = Counter(), Counter(), Counter()
    uniq_ids, pids = set(), set()
    for raw in rows:
        for name, value in raw.items():
            columns[name]["blank" if not value.strip() else "nonblank"] += 1
        cell = raw["product_specifications"].strip()
        if not cell:
            shapes["spec_blank"] += 1
        elif cell == '{"product_specification"=>nil}':
            shapes["spec_nil"] += 1
        elif cell.startswith('{"product_specification"=>['):
            shapes["spec_list"] += 1
        elif cell.startswith('{"product_specification"=>{'):
            shapes["spec_singleton"] += 1
        else:
            shapes["spec_other"] += 1
        uniq_ids.add(raw["uniq_id"])
        pids.add(raw["pid"])
    identities.update(unique_uniq_id=len(uniq_ids), unique_pid=len(pids))
    category_counts, coverage = Counter(), Counter()
    for item in observations:
        issue_counts.update(item.issues)
    for item in selection.canonical:
        fields = item.fields
        category_counts[fields["category"] or "unclassified"] += 1
        for name in ("brand", "category", "description", "colour", "material", "size"):
            if fields[name] is not None:
                coverage[name] += 1
                if fields["active"]:
                    coverage["active_" + name] += 1
    return {
        "source_sha256": source_sha256,
        "raw_rows": len(observations),
        "column_profiles": {name: dict(counts) for name, counts in sorted(columns.items())},
        "nested_shape_counts": dict(shapes),
        "identity_counts": dict(identities),
        "category_counts": dict(category_counts),
        "facet_coverage": dict(coverage),
        "selected_counts": dict(Counter(selection.dispositions.values())),
        "issue_counts": dict(issue_counts),
    }
