"""Stateful shopping dialogue over the existing validated retrieval and purchase services."""

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from time import monotonic

from shared.contracts.common import ErrorCode
from shared.contracts.shopping import ShoppingMemory

from .clients import DependencyUnavailable, RemoteError
from .errors import ServiceError
from .intent import blank_intent, canonical_text, extract_intent, validate_constraints
from .provider_contracts import ContractUnavailable, ContractViolation
from .workflow import FixedWorkflow

MORE = re.compile(
    r"\b(more (?:options|products|results)|alternatives|other options|different ones)\b"
)
SIMILAR = re.compile(r"\b(similar|like (?:this|that)|for this product)\b")
PRODUCT = re.compile(
    r"\b(shirts?|t-shirts?|watches|watch|shoes?|dresses|dress|sarees?|kurtas?|"
    r"laptops?|phones?|bags?|headphones?|earphones?|sofas?|chairs?|tables?|"
    r"jewellery|jewelry|sunglasses|books?|jeans|trousers|clothing|furniture)\b"
)
QUESTIONS = {
    "query_text": "What kind of product would you like? For example, a shirt, watch or bag.",
    "category": "Which product category do you mean? Size filters need an apparel category.",
    "size": "Which clothing size would you like? I can only match sizes recorded in the catalogue.",
    "colour": "Which single colour should I look for? You can also say ‘any colour’.",
    "material": "Which material should I use? Unknown materials cannot be assumed.",
    "brand": "Which brand do you mean? Please use a brand listed in the catalogue.",
    "max_price_minor": "What is your maximum budget in INR? For example, ‘under 1000 rupees’.",
    "currency": "The catalogue uses INR. What maximum budget in rupees should I use?",
    "unsupported_attribute": (
        "That attribute is not reliably recorded. Please describe the product using "
        "category, colour, material or budget."
    ),
    "constraints": (
        "Please give one clear set of preferences; "
        "I won't silently drop exclusions or conflicting filters."
    ),
    "explicit_control": (
        "Use the product and cart buttons to shop. "
        "Open your cart, select Review order, then confirm when you're ready."
    ),
    "reference": (
        "Which product do you mean? Choose ‘Find similar’ on a product, or say ‘the first one’."
    ),
    "limit": (
        "You've seen 200 options for this search. "
        "Refine your preferences to start a fresh result set."
    ),
}


@dataclass
class Resolution:
    result: object
    more: bool = False
    question: str | None = None
    selected_sku: str | None = None


def resolve(text, memory, dictionary):
    """Merge explicit refinements; never infer a purchase or relax a hard constraint."""
    normalized = canonical_text(text)
    reset = bool(re.search(r"\b(new search|start over|start again)\b", normalized))
    cleaned = re.sub(r"^(?:new search|start over|start again)[: ,]*", "", normalized)
    prior = None if reset else memory.intent
    more, similar = bool(MORE.search(cleaned)), bool(SIMILAR.search(cleaned))
    cheaper = bool(re.search(r"\bcheaper\b", cleaned))
    selected = memory.selected_sku
    ordinal = re.search(
        r"\b(?:the )?(first|second|third|fourth|fifth) (?:one|product|option)\b", cleaned
    )
    if ordinal:
        index = ["first", "second", "third", "fourth", "fifth"].index(ordinal[1])
        selected = memory.products[index]["sku"] if index < len(memory.products) else None
        similar = similar or not cheaper
    anchor = next((p for p in memory.products if p["sku"] == selected), None)
    if anchor is None and len(memory.products) == 1:
        anchor = memory.products[0]
    clears = set()
    for field, phrase in (
        ("colour", r"any colou?r|all colou?rs|remove (?:the )?colou?r filter"),
        ("brand", r"any brand|remove (?:the )?brand filter"),
        ("max_price_minor", r"any price|no budget limit|remove (?:the )?budget filter"),
    ):
        if re.search(phrase, cleaned):
            clears.add(field)
            cleaned = re.sub(phrase, "", cleaned).strip()
    if (
        prior
        and "max_price_minor" in memory.pending
        and re.fullmatch(r"(?:inr\s*)?\d+(?:\.\d{1,2})?", cleaned)
    ):
        cleaned = "at most " + cleaned + " rupees"
    parsed_text = re.sub(r"\bcheaper\b", "", cleaned) if cheaper else cleaned
    # A short answer is scoped by the question we just asked, including single-letter sizes.
    if memory.pending:
        slot = memory.pending[0]
        answers = {
            "size": dictionary["allowed_apparel_sizes"],
            "colour": dictionary["colours"],
            "material": dictionary["materials"],
            "brand": [v for b in dictionary["brands"] for v in (b["key"], b["label"])],
            "category": [v for r in dictionary["roots"] for v in (r["id"], r["label"])],
        }
        if cleaned in {canonical_text(v) for v in answers.get(slot, [])}:
            parsed_text = slot + " " + cleaned
    result = extract_intent(parsed_text, None, dictionary)
    explicit = result.intent or blank_intent(parsed_text)
    refinement = bool(prior) and (
        more
        or similar
        or cheaper
        or clears
        or memory.pending
        or (
            not PRODUCT.search(cleaned)
            and any(
                v is not None for k, v in explicit.items() if k not in {"query_text", "currency"}
            )
        )
        or re.match(r"^(only|make|change|keep|same|instead|under|below|at most)\b", cleaned)
    )
    intent = (
        {**prior, **{k: v for k, v in explicit.items() if v is not None and k != "query_text"}}
        if refinement
        else dict(explicit)
    )
    if refinement:
        intent["query_text"] = prior["query_text"]
        subject_answer = bool(PRODUCT.search(cleaned)) or (
            bool(re.search(r"[a-z]", cleaned))
            and not any(
                v is not None for k, v in explicit.items() if k not in {"query_text", "currency"}
            )
            and not re.search(r"\b(something|anything|gift|not sure)\b", cleaned)
        )
        if "query_text" in memory.pending and subject_answer:
            intent["query_text"] = cleaned
    for field in clears:
        intent[field] = None
    missing = [f for f in result.missing_fields if f not in clears]
    if refinement:
        for field in memory.pending:
            if field == "query_text" and not subject_answer:
                missing.append(field)
            elif field in {"category", "size", "colour", "material", "brand", "max_price_minor"}:
                answered = explicit.get(field) is not None or field in clears
                answered |= field == "max_price_minor" and cheaper
                answered |= field == "category" and intent.get("category") == "clothing"
                if not answered:
                    missing.append(field)
    if prior and (cheaper or clears) and "query_text" in missing:
        missing.remove("query_text")
    if "category" in missing and intent.get("category") == "clothing":
        missing.remove("category")
    if cheaper:
        candidates = [anchor] if anchor else memory.products
        prices = [p["price_minor"] for p in candidates if type(p.get("price_minor")) is int]
        if prices:
            bound = min(prices) - 1
            current = intent.get("max_price_minor")
            intent["max_price_minor"] = min(current, bound) if current is not None else bound
        else:
            missing.append("max_price_minor")
    if similar:
        if anchor:
            intent["query_text"] = anchor["title"]
            selected = anchor["sku"]
        else:
            missing.append("reference")
    if more and not prior:
        missing.append("query_text")
    if (more or similar) and len(memory.seen_skus) >= 200:
        missing.append("limit")
    if (
        not prior
        and not PRODUCT.search(cleaned)
        and re.search(
            r"\b(something|anything|gift|help me|not sure|recommend something)\b", cleaned
        )
    ):
        missing.append("query_text")
    if not cleaned and not clears and not (more or similar or cheaper):
        missing.append("query_text")
    issue = validate_constraints(intent, dictionary)
    if issue:
        missing.append(issue)
    missing = list(dict.fromkeys(missing))
    question = (
        QUESTIONS.get(missing[0], "Could you be more specific about the product or filter?")
        if missing
        else None
    )
    result = replace(
        result,
        intent=intent,
        missing_fields=missing,
        outcome="clarification_required" if missing else "valid",
        reason_code="UNRESOLVED_CONSTRAINT" if missing else None,
        extractor_source="clarification" if missing else "rules",
    )
    return Resolution(result, more=more or similar, question=question, selected_sku=selected)


class ShoppingWorkflow(FixedWorkflow):
    def __init__(self, *args, shopping_provider=None, **kwargs):
        super().__init__(*args, **kwargs)
        if shopping_provider is not None:
            from .shopping_llm import GeminiShoppingProvider

            if shopping_provider.mode != self.mode or (
                self.mode == "real" and type(shopping_provider) is not GeminiShoppingProvider
            ):
                raise ValueError("shopping provider must match the service execution mode")
        self.shopping_provider = shopping_provider

    def order_pipeline(self, order_id, context):
        # Authorize with Orders first. Never return a namespace-wide Gold response to a browser.
        order = self.store_call("order_status", context, order_id=order_id)
        result = {
            "order_id": order_id,
            "order_version": order["order_version"],
            "status": "pending",
            "generation": None,
            "checked_at": datetime.now(UTC),
        }
        day = (
            datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
            .astimezone(UTC)
            .date()
        )
        try:
            gold = self.call(
                "gold",
                context,
                table="order_fact",
                params={
                    "namespace": context.namespace,
                    "date_from": day.isoformat(),
                    "date_to": (day + timedelta(days=1)).isoformat(),
                },
            )
            matches = [r for r in gold["rows"] if r.get("order_id") == order_id]
            if not matches:
                return result
            if len(matches) != 1 or type(matches[0].get("order_version")) is not int:
                raise ContractViolation("Invalid Gold order identity/version")
            row = matches[0]
            if row.get("namespace") != context.namespace:
                raise ContractViolation("Gold order namespace mismatch")
            if row["order_version"] != order["order_version"]:
                # A later version can arrive while the two independent reads run.
                return result
            fields = (
                "order_id",
                "user_id",
                "session_id",
                "quote_id",
                "total_amount_minor",
                "currency",
                "failure_code",
            )
            # The canonical ORDER_CANCELLED event has no participant ID fields;
            # Gold represents those absent facts as null. Audit participants via
            # their owner APIs; never require a cancelled event to invent them.
            if order["status"] == "CONFIRMED":
                fields += ("reservation_id", "payment_id")
            if (
                row.get("order_status") != order["status"]
                or type(row.get("total_amount_minor")) is not int
                or any(row.get(k) != order.get(k) for k in fields)
            ):
                raise ContractViolation("Gold order does not match its authoritative snapshot")
            return {**result, "status": "visible", "generation": gold["generation"]}
        except (DependencyUnavailable, RemoteError, ContractUnavailable, ContractViolation):
            return {**result, "status": "unavailable"}

    def store_call(self, name, context, **kwargs):
        try:
            if name == "browse" and kwargs.get("params", {}).get("q", "").strip():
                return self.browse_search(context, kwargs["params"])
            return self.call(name, context, **kwargs)
        except RemoteError as error:
            raise ServiceError(
                error.status, error.payload.error.code, error.payload.error.message
            ) from error
        except (DependencyUnavailable, ContractUnavailable, ContractViolation) as error:
            raise ServiceError(
                503,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "The shopping service is unavailable. Please retry.",
            ) from error

    def browse_search(self, context, params):
        """Rank at most 20 real products with hybrid retrieval and recorded hard filters.

        Empty-query browsing keeps the full catalogue pagination. Query pages represent
        only this bounded recommendation set; no claim about a global match count.
        """
        deadline = monotonic() + 8
        context = context.model_copy(
            update={"session_id": context.session_id or context.request_id}
        )
        dictionary = self.call(
            "facets", context, deadline=deadline, params={"namespace": context.namespace}
        )
        parsed = extract_intent(params["q"], context, dictionary)
        if parsed.missing_fields:
            raise ServiceError(
                422,
                ErrorCode.UNSUPPORTED_FILTER,
                "Please describe the product in chat so we can clarify your preferences.",
            )
        intent = dict(parsed.intent)
        if params.get("category") is not None:
            if intent.get("category") not in (None, params["category"]):
                raise ServiceError(
                    422,
                    ErrorCode.UNSUPPORTED_FILTER,
                    "Your search and category filter differ. Choose a matching category.",
                )
            intent["category"] = params["category"]
        if params.get("max_price_minor") is not None:
            bounds = [params["max_price_minor"]]
            if intent.get("max_price_minor") is not None:
                bounds.append(intent["max_price_minor"])
            intent["max_price_minor"] = min(bounds)
        result = self._search(
            intent,
            dictionary,
            context,
            context.request_id,
            deadline,
            mode="hybrid_exact",
            top_k=20,
        )
        hits = result["hits"]
        if params["sort"] != "relevance":
            hits = sorted(
                hits,
                key=lambda hit: (
                    hit["price_minor"] * (-1 if params["sort"] == "price_desc" else 1),
                    hit["sku"],
                ),
            )
        offset, limit = params["offset"], params["limit"]
        return {
            "items": hits[offset : offset + limit],
            "total": len(hits),
            "offset": offset,
            "limit": limit,
        }

    def dispatch_turn(self, session_id, request, context, key):
        if request.mode == "assist":
            from .shopping_dialogue import dispatch_turn

            return dispatch_turn(self, session_id, request, context, key)
        started = monotonic()

        def handle(body, scoped, raw):
            memory = ShoppingMemory.model_validate(raw)
            options = {"mode": body.retrieval_mode or memory.retrieval_mode}
            resolution = None

            def prepare(text, dictionary):
                nonlocal resolution
                if body.retrieval_mode is None and memory.intent is None:
                    capabilities = self.call("capabilities", scoped, deadline=started + 3)
                    options["mode"] = (
                        "hybrid_exact"
                        if "hybrid_exact" in capabilities["search_modes"]
                        else "lexical"
                    )
                if body.selected_sku:
                    product = next(
                        (p for p in memory.products if p["sku"] == body.selected_sku), None
                    )
                    if product is None:
                        response = self.store_call(
                            "product", scoped, sku=body.selected_sku, deadline=started + 3
                        )
                        product = response["product"]
                        memory.products = [{**product, "sku": body.selected_sku}]
                    memory.selected_sku = body.selected_sku
                resolution = resolve(text, memory, dictionary)
                if resolution.more:
                    options["exclude_skus"] = list(
                        dict.fromkeys(
                            memory.seen_skus
                            + ([resolution.selected_sku] if resolution.selected_sku else [])
                        )
                    )[:200]
                return resolution.result

            execution = self._turn(
                body, scoped, key, started, prepare=prepare, search_options=options
            )
            response = execution.response
            if resolution and response.outcome != "dependency_error":
                memory.intent = resolution.result.intent
                memory.pending = resolution.result.missing_fields
                memory.selected_sku = resolution.selected_sku
                memory.retrieval_mode = options["mode"]
                if response.outcome == "success":
                    memory.products = response.products
                    seen = memory.seen_skus if resolution.more else []
                    memory.seen_skus = list(
                        dict.fromkeys(seen + [p["sku"] for p in response.products])
                    )[:200]
                    summary = (
                        "Here are more matching options."
                        if resolution.more
                        else "Here are products matching your preferences."
                    )
                    response = response.model_copy(
                        update={
                            "response_text": summary
                            if response.products
                            else "I couldn't find more matches with those preferences. "
                            "You can explicitly change a filter or start a new search."
                        }
                    )
                elif resolution.question:
                    response = response.model_copy(update={"response_text": resolution.question})
            memory.messages = (
                memory.messages
                + [
                    {"role": "user", "text": body.text},
                    {"role": "assistant", "text": response.response_text},
                ]
            )[-40:]
            return replace(
                execution, response=response, shopping_context=memory.model_dump(mode="json")
            )

        return self.state.record_turn(session_id, request, context, key, handle, shopping=True)
