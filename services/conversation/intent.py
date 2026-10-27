"""Conservative rules over a provider-supplied, versioned facet dictionary.

No scenario IDs, catalogue fixtures, model SDK, or product descriptions enter
extraction. Unknown explicit constraints require clarification before retrieval.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from time import monotonic

VERSION = "rules-p7-v1"
SLOTS = ("category", "size", "colour", "material", "max_price_minor", "occasion")
SIZE_ALIASES = {
    "small": "S",
    "medium": "M",
    "large": "L",
    "extra large": "XL",
    "free size": "FREE_SIZE",
    "one size": "ONE_SIZE",
}


@dataclass(frozen=True)
class IntentResult:
    outcome: str
    intent: dict | None
    missing_fields: list[str]
    reason_code: str | None
    extractor_version: str = VERSION
    extractor_source: str = "rules"
    llm_call_count: int = 0
    parse_ms: float = 0
    llm_ms: None = None
    model_usage: None = None


def blank_intent(text):
    return {
        "query_text": text,
        **dict.fromkeys(SLOTS),
        "currency": "INR",
        "brand": None,
        "category_path_prefix": None,
    }


def phrases(text, mapping):
    """Longest non-overlapping dictionary matches preserve compound values."""
    matches, remaining = set(), text
    for phrase in sorted(mapping, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
        if re.search(pattern, remaining):
            matches.add(mapping[phrase])
            remaining = re.sub(pattern, " ", remaining)
    return matches


def validate_constraints(intent, dictionary):
    """Validate structured controls without running text extraction."""
    allowed = {
        "category": [r["id"] for r in dictionary["roots"]],
        "size": dictionary["allowed_apparel_sizes"],
        "colour": dictionary["colours"],
        "material": dictionary["materials"],
        "brand": [b["key"] for b in dictionary["brands"]],
        "category_path_prefix": dictionary["path_prefixes"],
    }
    for field, values in allowed.items():
        if intent.get(field) is not None and intent[field] not in values:
            return field
    if intent.get("size") is not None and intent.get("category") != "clothing":
        return "category"
    bound = intent.get("max_price_minor")
    if bound is not None and (type(bound) is not int or not 0 <= bound < 2**63):
        return "max_price_minor"
    if intent.get("currency", "INR") != "INR":
        return "currency"
    return None


def extract_intent(text, context, dictionary):
    """Parse real input deterministically; context is identity, never a label lookup."""
    started = monotonic()
    intent, missing = blank_intent(text), []
    normalized = " ".join(text.casefold().split())

    def finish():
        return IntentResult(
            outcome="clarification_required" if missing else "valid",
            intent=intent,
            missing_fields=sorted(set(missing)),
            reason_code="UNRESOLVED_CONSTRAINT" if missing else None,
            extractor_source="clarification" if missing else "rules",
            parse_ms=(monotonic() - started) * 1000,
        )

    if not normalized:
        missing.append("query_text")
    # Free text never invokes a mutation, even if it includes valid-looking IDs.
    if re.search(r"\b(checkout|purchase|buy|cart|quote|order|payment)\b", normalized):
        missing.append("explicit_control")
        return finish()
    # A compound exact value can already guarantee a stated exclusion. Discard
    # only that redundant exclusion, never an independent hard constraint.
    contrast = re.search(r"[,;]\s*(?:not exact|do not assume it is)\s+([\w ]+)\.?$", normalized)
    if contrast:
        positive, excluded = normalized[: contrast.start()], contrast[1].rstrip(".")
        for values in (dictionary["materials"], dictionary["colours"]):
            found = phrases(positive, {v.casefold(): v for v in values})
            if len(found) == 1 and excluded in values and excluded not in found:
                normalized = positive
                break
    # Negation/disjunction can alter hard eligibility. Ask instead of guessing.
    # An inclusive monetary phrase is not a disjunction of hard filters.
    constraints_text = normalized.replace("rupees or less", "rupees inclusive")
    if re.search(r"\b(not|except|without|either|or)\b", constraints_text):
        missing.append("constraints")
    if re.search(r"\b(clarify|ask|confirm)\b.*\b(category|clothing)\b", normalized):
        missing.append("category")
    maps = {
        "category": {
            alias.casefold(): root["id"]
            for root in dictionary["roots"]
            for alias in (root["id"], root["label"])
        },
        "colour": {v.casefold(): v for v in dictionary["colours"]},
        "material": {v.casefold(): v for v in dictionary["materials"]},
        "brand": {
            alias.casefold(): b["key"]
            for b in dictionary["brands"]
            for alias in (b["key"], b["label"])
        },
        "size": {v.casefold(): v for v in dictionary["allowed_apparel_sizes"]},
    }
    maps["size"].update(
        {k: v for k, v in SIZE_ALIASES.items() if v in dictionary["allowed_apparel_sizes"]}
    )
    if "grey" in dictionary["colours"]:
        maps["colour"]["gray"] = "grey"
    for field, mapping in maps.items():
        # Bare single-letter sizes are recognized only after an explicit size cue.
        source = normalized
        if field == "size":
            source = re.sub(r"\b[a-z]\b", " ", source)
            explicit = re.search(r"\bsize(?:\s*(?:=|:)\s*|\s+)([a-z]+)\b", normalized)
            if explicit:
                source += " " + explicit[1]
        found = phrases(source, mapping)
        if len(found) == 1:
            intent[field] = found.pop()
        elif found:
            missing.append(field)
    for field, cue in (
        ("size", "size"),
        ("colour", "colou?r"),
        ("material", "material|fabric"),
        ("brand", "brand"),
        ("category", "category"),
    ):
        explicit = re.search(r"\b(?:" + cue + r")(?:\s*(?:=|:)\s*|\s+(?:is\s+)?)(\w+)", normalized)
        if explicit:
            if intent[field] is None or not any(
                phrase.split()[0] == explicit[1] for phrase in maps[field]
            ):
                missing.append(field)
    if intent["size"] is not None and intent["category"] != "clothing":
        missing.append("category")
    # Unsupported explicit attributes cannot be silently passed as loose keywords.
    if re.search(r"\b(waterproof|sleeve|dimensions|shoe size|rating|seller)\b", normalized):
        missing.append("unsupported_attribute")
    price = re.findall(
        r"\b(under|below|at most|within a budget of|up to)\s+(?:inr\s*)?"
        r"(\d[\d,]*(?:\.\d+)?)(?![\w.,])\s*(?:rupees|inr|rs\b)?",
        normalized,
    )
    suffix = re.findall(r"\b(\d+(?:\.\d+)?)\s+rupees or less\b", normalized)
    price.extend(("at most", amount) for amount in suffix)
    if len(price) > 1:
        missing.append("max_price_minor")
    elif price:
        relation, raw = price[0]
        try:
            if "," in raw and not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
                raise InvalidOperation
            minor = Decimal(raw.replace(",", "")) * 100
            if minor != minor.to_integral_value() or not 0 <= minor < 2**63:
                raise InvalidOperation
            bound = int(minor) - (1 if relation in {"under", "below"} else 0)
            if bound < 0:
                raise InvalidOperation
            intent["max_price_minor"] = bound
        except InvalidOperation:
            missing.append("max_price_minor")
    elif re.search(r"\b(price|budget|rupees|inr|rs|under|below|cheaper)\b|[₹$€]", normalized):
        missing.append("max_price_minor")
    occasion = re.search(r"\bfor (?:a |an )?(party|celebration|casual|formal)\b", normalized)
    if occasion:
        intent["occasion"] = occasion[1]
    issue = validate_constraints(intent, dictionary)
    if issue:
        missing.append(issue)
    return finish()
