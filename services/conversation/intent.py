"""Conservative rules over a provider-supplied, versioned facet dictionary.

No scenario IDs, catalogue fixtures, model SDK, or product descriptions enter
extraction. Unknown explicit constraints require clarification before retrieval.
"""

import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal, InvalidOperation
from time import monotonic

VERSION = "rules-p7-v2"
SLOTS = ("category", "size", "colour", "material", "max_price_minor", "occasion")
SIZE_ALIASES = {
    "small": "S",
    "medium": "M",
    "large": "L",
    "extra large": "XL",
    "free size": "FREE_SIZE",
    "one size": "ONE_SIZE",
}
# This is extraction grammar, not a catalogue vocabulary. Uncued source values
# such as "skin", "104" or product nouns stay in query_text. Every accepted
# modifier must still match a whole value in the provider's dictionary.
IMPLICIT_MODIFIERS = {
    "colour": set(
        "black white blue red green yellow orange pink purple brown grey gray beige "
        "navy maroon violet indigo cyan magenta gold golden silver multicolor "
        "light dark pale bright".split()
    ),
    "material": set(
        "cotton lycra wool silk linen polyester nylon rayon viscose elastane spandex "
        "leather suede denim velvet satin acrylic wooden wood steel stainless metal "
        "plastic glass ceramic rubber blend blended pure 100%".split()
    ),
}
FACET_CUES = {
    "brand": "brand|by",
    "colour": "colou?r",
    "material": "material|fabric|made of",
    "size": r"(?<!free )(?<!one )size",
    "category": "category",
}


def canonical_text(value):
    """Consumer key comparison follows file 08: NFC, whitespace, casefold."""
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def explicit_facets(text, maps):
    """Bind cued whole values and mask them from unrelated slot extraction.

    A recognized prefix cannot swallow an unsupported compound (size M/L,
    material cotton unknown). Separate constraints with a cue or a clause.
    """
    pattern = (
        r"\b(?:"
        + "|".join(f"(?P<{field}>{cue})" for field, cue in FACET_CUES.items())
        + r")\b(?:\s*(?:=|:)\s*|\s+(?:is\s+)?)?"
    )
    next_clause = (
        r"(?:for|in|under|below|at most|up to|within a budget of|brand|by|"
        r"colou?r|material|fabric|made of|size|category)\b"
    )
    boundary = r"\s*(?:$|[,;.!?]|\b(?:and\s+)?" + next_clause + ")"
    values, missing, masked, consumed = {}, [], list(text), 0
    for cue in re.finditer(pattern, text):
        if cue.start() < consumed:
            continue
        field = cue.lastgroup
        tail = text[cue.end() :]
        found = next(
            (
                phrase
                for phrase in sorted(maps[field], key=len, reverse=True)
                if re.match(re.escape(phrase) + r"(?!\w)", tail)
            ),
            None,
        )
        if found is None or not re.match(boundary, tail[len(found) :]):
            missing.append(field)
            end = cue.end() + len(re.split(r"[,;.!?]|\band\b", tail, maxsplit=1)[0])
        else:
            values.setdefault(field, set()).add(maps[field][found])
            end = cue.end() + len(found)
        masked[cue.start() : end] = " " * (end - cue.start())
        consumed = end
    return values, missing, "".join(masked)


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
    llm_ms: float | None = None
    model_usage: dict | None = None
    rejected_output: str | None = dataclass_field(default=None, repr=False)


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
    normalized = canonical_text(text)

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
            canonical_text(alias): root["id"]
            for root in dictionary["roots"]
            for alias in (root["id"], root["label"])
        },
        "colour": {canonical_text(v): v for v in dictionary["colours"]},
        "material": {canonical_text(v): v for v in dictionary["materials"]},
        "brand": {
            canonical_text(alias): b["key"]
            for b in dictionary["brands"]
            for alias in (b["key"], b["label"])
        },
        "size": {canonical_text(v): v for v in dictionary["allowed_apparel_sizes"]},
    }
    maps["size"].update(
        {k: v for k, v in SIZE_ALIASES.items() if v in dictionary["allowed_apparel_sizes"]}
    )
    if "grey" in dictionary["colours"]:
        maps["colour"]["gray"] = "grey"
    explicit, issues, source = explicit_facets(normalized, maps)
    missing.extend(issues)
    for field, mapping in maps.items():
        # Brands always need a cue. Uncommon facet values stay loose query terms
        # unless the user names the slot, avoiding noisy dictionary collisions.
        implicit_source = source if field != "brand" else ""
        if field == "size":
            implicit_source = re.sub(r"\b[a-z]\b", " ", implicit_source)
        found = phrases(implicit_source, mapping) if implicit_source.strip() else set()
        if field in IMPLICIT_MODIFIERS:
            found = {
                value
                for value in found
                if set(canonical_text(value).split()) <= IMPLICIT_MODIFIERS[field]
            }
        found.update(explicit.get(field, ()))
        if len(found) == 1:
            intent[field] = found.pop()
        elif found:
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
    # Every monetary clause must be understood. A recognized upper bound does
    # not license dropping a second malformed bound, minimum, or foreign unit.
    cues = re.findall(r"\b(?:under|below|at most|within a budget of|up to)\b", normalized)
    if len(cues) + len(suffix) != len(price) or re.search(
        r"\b(?:above|over|at least|more than|between|minimum)\s+(?:inr\s*)?[-\d]",
        normalized,
    ):
        missing.append("max_price_minor")
    if re.search(r"\b(?:usd|eur|gbp|jpy|dollars?|euros?|pounds?|yen)\b|[$€£¥]", normalized):
        missing.append("currency")
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
