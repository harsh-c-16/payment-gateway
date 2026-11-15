"""Execute a conversational model's bounded read-only plan through owner contracts."""

import re
from dataclasses import replace
from time import monotonic

from shared.contracts.shopping import ShoppingMemory

from .intent import (
    PRODUCT_NOUNS,
    IntentResult,
    blank_intent,
    canonical_text,
    extract_intent,
    validate_constraints,
)
from .intent_fallback import ModelFailure
from .shopping import QUESTIONS
from .shopping_llm import PROMPT_REVISION, TURN_SECONDS

RESPONSES = {
    "greeting": "Hello! Tell me what you're shopping for, including any colour or budget.",
    "thanks": "You're welcome! Tell me if you'd like to refine your search or find something else.",
    "help": "I can find catalogue products, remember your preferences, show alternatives and "
    "compare recorded product details. What would you like to find?",
    "checkout": "Add your favourite products to the cart, then select Review order. "
    "Check the total and choose Place demo order when you're ready.",
    "out_of_scope": "I can help with shopping in this catalogue. What product would you like?",
}
FAILURES = {
    "MODEL_DISABLED": "AI chat is unavailable. Please try again later.",
    "MODEL_TIMEOUT": "AI chat took too long. Please try again.",
    "MODEL_HTTP_ERROR": "The AI provider rejected this request (key, quota or service error). "
    "Please try again later.",
    "MODEL_PREVIOUS_ATTEMPT": "This message already used its model attempt. "
    "Please send it as a new message.",
    "MODEL_INVALID_OUTPUT": "The AI returned an invalid shopping instruction. "
    "Please rephrase your message.",
    "MODEL_UNSUPPORTED_INTENT": "I couldn't apply that to this catalogue. Name the product, "
    "colour or budget, or choose New search to start over.",
    "MODEL_CONSTRAINT_CHANGED": "I wasn't sure which earlier preferences to keep. Choose New "
    "search to start over, or tell me which filter to change.",
    "MODEL_REFUSAL": RESPONSES["out_of_scope"],
    "MODEL_UNAVAILABLE": "AI chat couldn't reach the AI provider. Please try again.",
}
NEW_SEARCH = re.compile(r"\s*new search\b", re.I)
GREETING = re.compile(r"\s*(hi+|hello|hey+|namaste|good (morning|afternoon|evening))[\s!.]*", re.I)
THANKS = re.compile(r"\s*(thanks|thank you|thx|ty)[\s!.]*", re.I)
REMOVAL = r"\b(any|all|no|remove|clear|ignore|forget|don't|do not|doesn't|does not)\b"
# Only a maximum price is a supported filter; minimum budgets are asked about, not dropped.
MIN_BUDGET = re.compile(
    r"\b(above|over|at least|more than|minimum|min|between)\s*(?:₹|rs\.?|inr)?\s*\d", re.I
)
CLARIFY_TEXT = {
    "min_price": "I can only filter by a maximum price. What's the most you'd like to spend, "
    "for example ‘under 1000 rupees’?",
    "category": "I can search for one kind of product at a time. Which should I look for first?",
}


def provider_error_text(code, usage):
    status = (usage or {}).get("http_status")
    if status == 429:
        return "AI chat reached its usage limit. Please try again later."
    if status in {500, 502, 503, 504}:
        return "AI chat is busy. Please try again shortly."
    if status in {401, 403}:
        return (
            "Gemini did not accept the server credential. Check the private API key configuration."
        )
    if status == 404:
        return "The configured Gemini model is unavailable. Check SHOPPING_LLM_MODEL on the server."
    return FAILURES.get(
        code,
        "AI chat is unavailable. Please try again.",
    )


def named_categories(text):
    """Root categories named by product nouns, e.g. {"clothing", "footwear"} for shirt and shoes."""
    folded = canonical_text(text)
    return {
        root
        for root, nouns in PRODUCT_NOUNS.items()
        if re.search(r"(?<![\w-])(?:" + nouns + r")(?![\w-])", folded)
    }


def stated_category(text, dictionary):
    parsed = extract_intent(text, None, dictionary)
    return None if "category" in parsed.missing_fields else parsed.intent.get("category")


def starts_new_search(arguments, memory, text, dictionary):
    """New search control, a model-declared reset, or a different named product category.

    Refinements and answers to a question keep earlier filters; a reply with no matches
    names them all, so a kept filter is never hidden from the shopper.
    """
    if NEW_SEARCH.match(text) or getattr(arguments, "new_search", False):
        return True
    if not memory.intent:
        return False
    new = stated_category(text, dictionary)
    old = memory.intent.get("category") or stated_category(
        memory.intent.get("query_text") or "", dictionary
    )
    return new is not None and old is not None and new != old


def merged_intent(arguments, memory, text, dictionary):
    """Omitted fields preserve hard filters; every value still needs M2 vocabulary.

    A new search starts blank, so earlier colour or budget never leaks into another
    product. Otherwise an earlier constraint changes only when the shopper names the
    new value or explicitly removes it; an unrequested model change is ignored.
    """
    reset = starts_new_search(arguments, memory, text, dictionary)
    intent = dict(memory.intent) if memory.intent and not reset else blank_intent("")
    changes = arguments.filters.model_dump(exclude_unset=True)
    for field, value in list(changes.items()):
        previous = intent.get(field)
        if previous is None or value == previous:
            continue
        if value is None:
            names = {"colour": "colou?r", "max_price_minor": "budget|price|limit"}
            requested = re.search(REMOVAL, text, re.I) and re.search(
                names.get(field, field), text, re.I
            )
        elif field == "max_price_minor":
            requested = bool(re.search(r"\d", text)) or getattr(arguments, "cheaper", False)
        else:
            requested = str(value).casefold() in text.casefold()
        if not requested:
            del changes[field]
    intent.update(changes)
    if getattr(arguments, "more", False) and memory.intent and not reset:
        intent["query_text"] = memory.intent["query_text"]
    elif arguments.query.strip():
        query = NEW_SEARCH.sub("", arguments.query).strip(" :")
        spoken = NEW_SEARCH.sub("", text).strip(" :")
        # The model can echo an earlier product ("watches" for "red saree"); the
        # shopper's own words win when they name a different product.
        said = stated_category(spoken, dictionary)
        if said is not None and stated_category(query, dictionary) not in (None, said):
            query = spoken
        intent["query_text"] = query or intent["query_text"]
    # Unambiguous rule-extracted filters, including the named product category, are hard
    # constraints the model cannot drop or change. Strict "under" bounds come from rules.
    explicit = extract_intent(text, None, dictionary)
    for field in (
        "category",
        "category_path_prefix",
        "colour",
        "material",
        "size",
        "brand",
        "max_price_minor",
    ):
        value = explicit.intent.get(field)
        if value is not None and field not in explicit.missing_fields:
            intent[field] = value
    issue = validate_constraints(intent, dictionary)
    if issue:
        raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
    return intent


def product_reference(memory, rank):
    if rank is None and memory.selected_sku:
        return next((p for p in memory.products if p["sku"] == memory.selected_sku), None)
    if rank is not None and rank <= len(memory.products):
        return memory.products[rank - 1]
    return None


def describe_product(response):
    p, stock = response["product"], response["stock"]
    price = (
        f"{p['currency']} {p['price_minor'] / 100:,.2f}" if p["price_minor"] else "unrecorded price"
    )
    recorded = "; ".join(
        f"{k}: {p[k] if p[k] is not None else 'not recorded'}"
        for k in ("brand", "colour", "material", "size")
    )
    available = stock["available"] if stock else "unknown"
    return f"{p['title']} — {price}; {recorded}; displayed availability: {available}."


def dispatch_turn(workflow, session_id, request, context, key):
    started = monotonic()

    def handle(body, scoped, raw):
        memory = ShoppingMemory.model_validate(raw)
        provider = workflow.shopping_provider
        options = {"mode": body.retrieval_mode or memory.retrieval_mode}
        info = {
            "text": None,
            "failure": None,
            "intent": None,
            "pending": [],
            "search": False,
            "more": False,
            "selected": memory.selected_sku,
        }
        model_config = provider.provenance() if provider else {}
        tools = []

        def prepare(text, dictionary):
            calls, llm_ms, usage = 0, None, None
            tick = monotonic()

            def clarify(field, reason="UNRESOLVED_CONSTRAINT", intent=None):
                info["pending"] = ["max_price_minor" if field == "min_price" else field]
                info["text"] = CLARIFY_TEXT.get(field) or QUESTIONS[field]
                return IntentResult(
                    outcome="clarification_required",
                    intent=intent or memory.intent,
                    missing_fields=[field],
                    reason_code=reason,
                    extractor_version=PROMPT_REVISION,
                    extractor_source="llm" if calls else "clarification",
                    llm_call_count=calls,
                    llm_ms=llm_ms,
                    model_usage=usage,
                )

            # Greetings and thanks need no model call and must never reuse old results.
            courtesy = (
                "greeting"
                if GREETING.fullmatch(text)
                else "thanks"
                if THANKS.fullmatch(text)
                else None
            )
            if courtesy:
                info["text"] = RESPONSES[courtesy]
                return IntentResult(
                    outcome="clarification_required",
                    intent=memory.intent,
                    missing_fields=[],
                    reason_code="MODEL_CLARIFICATION",
                    extractor_version=PROMPT_REVISION,
                    extractor_source="rules",
                    llm_call_count=0,
                )
            try:
                if provider is None:
                    raise ModelFailure("MODEL_DISABLED")
                if body.retrieval_mode is None and memory.intent is None:
                    caps = workflow.call(
                        "capabilities", scoped, deadline=started + TURN_SECONDS, turn_tools=tools
                    )
                    options["mode"] = (
                        "hybrid_exact" if "hybrid_exact" in caps["search_modes"] else "lexical"
                    )
                if body.selected_sku:
                    # UI selection is a reference, never an arbitrary tool target.
                    selected = next(
                        (p for p in memory.products if p["sku"] == body.selected_sku), None
                    )
                    if selected is None:
                        selected = workflow.call(
                            "product",
                            scoped,
                            sku=body.selected_sku,
                            deadline=started + TURN_SECONDS,
                            turn_tools=tools,
                        )["product"]
                        memory.products = [selected]
                    memory.selected_sku = body.selected_sku
                reservation = workflow.state.claim_intent_attempt(body, scoped, model_config)
                if not reservation["claimed"]:
                    calls = 1
                    raise ModelFailure("MODEL_PREVIOUS_ATTEMPT")
                calls = 1
                tick = monotonic()
                try:
                    plan = provider.plan(
                        text, memory, dictionary, deadline=started + TURN_SECONDS - 3
                    )
                finally:
                    llm_ms = (monotonic() - tick) * 1000
                usage = plan.usage
                args = plan.arguments
                if plan.name in {"search_catalog", "ask_question"}:
                    reset = starts_new_search(args, memory, text, dictionary)
                    intent = merged_intent(args, memory, text, dictionary)
                    info["intent"] = intent
                    if reset:
                        info["selected"] = None
                    if plan.name == "ask_question":
                        info["text"], info["pending"] = args.question, [args.field]
                    else:
                        parsed = extract_intent(text, None, dictionary)
                        cleared = {
                            k
                            for k, v in args.filters.model_dump(exclude_unset=True).items()
                            if v is None
                        }
                        issue = next(
                            (
                                f
                                for f in parsed.missing_fields
                                if f not in cleared
                                and f
                                in {
                                    "constraints",
                                    "unsupported_attribute",
                                    "size",
                                    "colour",
                                    "material",
                                    "brand",
                                }
                            ),
                            None,
                        )
                        if MIN_BUDGET.search(text):
                            return clarify("min_price", intent=intent)
                        if len(named_categories(text)) > 1:
                            return clarify("category", intent=intent)
                        if issue:
                            return clarify(issue, intent=intent)
                        # A new search never compares against earlier results.
                        referenced = body.selected_sku or (args.reference is not None and not reset)
                        anchor = product_reference(memory, args.reference) if referenced else None
                        if referenced:
                            if anchor is None:
                                return clarify("reference", intent=intent)
                            info["selected"] = anchor["sku"]
                            # Retain the product subject instead of using unrelated title keywords.
                            if not intent["query_text"]:
                                intent["query_text"] = anchor["title"]
                        if args.cheaper:
                            # After a reset, "cheaper" has no earlier results to compare with.
                            choices = [anchor] if anchor else ([] if reset else memory.products)
                            prices = [
                                p["price_minor"]
                                for p in choices
                                if type(p.get("price_minor")) is int
                            ]
                            if not prices:
                                return clarify("query_text")
                            intent["max_price_minor"] = min(
                                min(prices) - 1,
                                intent["max_price_minor"]
                                if intent["max_price_minor"] is not None
                                else 2**63 - 1,
                            )
                        more = (args.more and not reset) or anchor is not None
                        if more:
                            if len(memory.seen_skus) >= 200:
                                info["text"] = (
                                    "You've seen every match for these preferences. "
                                    "Change a filter or choose New search."
                                )
                                return IntentResult(
                                    outcome="clarification_required",
                                    intent=intent,
                                    missing_fields=[],
                                    reason_code="MODEL_CLARIFICATION",
                                    extractor_version=PROMPT_REVISION,
                                    extractor_source="llm",
                                    llm_call_count=1,
                                    llm_ms=llm_ms,
                                    model_usage=usage,
                                )
                            options["exclude_skus"] = list(
                                dict.fromkeys(
                                    memory.seen_skus + ([anchor["sku"]] if anchor else [])
                                )
                            )[:200]
                        if not intent["query_text"].strip():
                            return clarify("query_text", intent=intent)
                        info["search"], info["more"] = True, more
                elif plan.name == "product_details":
                    descriptions = []
                    for rank in dict.fromkeys(args.references):
                        product = product_reference(memory, rank)
                        if product is None:
                            return clarify("reference")
                        response = workflow.call(
                            "product",
                            scoped,
                            sku=product["sku"],
                            deadline=started + TURN_SECONDS,
                            turn_tools=tools,
                        )
                        if response["product"]["sku"] != product["sku"] or (
                            response["stock"] is not None
                            and response["stock"]["sku"] != product["sku"]
                        ):
                            raise ModelFailure("MODEL_INVALID_OUTPUT")
                        descriptions.append(describe_product(response))
                        info["selected"] = product["sku"]
                    info["text"] = (
                        "\n".join(descriptions)
                        + "\nWe check availability again when you place your order."
                    )
                else:
                    info["text"] = RESPONSES[args.topic]
                return IntentResult(
                    outcome="valid" if info["search"] else "clarification_required",
                    intent=info["intent"] or memory.intent,
                    missing_fields=info["pending"],
                    reason_code=None if info["search"] else "MODEL_CLARIFICATION",
                    extractor_version=PROMPT_REVISION,
                    extractor_source="llm",
                    llm_call_count=1,
                    llm_ms=llm_ms,
                    model_usage=usage,
                )
            except (ModelFailure, TimeoutError) as error:
                code = error.code if isinstance(error, ModelFailure) else "MODEL_TIMEOUT"
                info["failure"] = provider_error_text(code, getattr(error, "usage", usage))
                return IntentResult(
                    outcome="clarification_required",
                    intent=memory.intent,
                    missing_fields=[],
                    reason_code=code,
                    extractor_version=PROMPT_REVISION,
                    extractor_source="clarification",
                    llm_call_count=calls,
                    llm_ms=llm_ms,
                    model_usage=getattr(error, "usage", usage),
                )

        execution = workflow._turn(
            body,
            scoped,
            key,
            started,
            prepare=prepare,
            search_options=options,
            deadline_seconds=TURN_SECONDS,
            intent_fallback=False,
            model_config=model_config,
            prepared_tools=tools,
        )
        response = execution.response
        if info["failure"]:
            response = response.model_copy(
                update={"outcome": "dependency_error", "response_text": info["failure"]}
            )
        elif response.outcome != "dependency_error":
            memory.intent = info["intent"] or memory.intent
            memory.pending, memory.selected_sku = info["pending"], info["selected"]
            memory.retrieval_mode = options["mode"]
            if info["search"]:
                memory.products = response.products
                memory.seen_skus = list(
                    dict.fromkeys(
                        (memory.seen_skus if info["more"] else [])
                        + [p["sku"] for p in response.products]
                    )
                )[:200]
                intent = memory.intent
                preferences = [intent["query_text"]] + [
                    f"{k}: {intent[k]}"
                    for k in ("colour", "material", "size", "brand")
                    if intent.get(k) is not None
                ]
                if intent.get("max_price_minor") is not None:
                    preferences.append(f"up to INR {intent['max_price_minor'] / 100:,.2f}")
                more_label = "more " if info["more"] else ""
                count = len(response.products)
                intro = f"I found {count} {more_label}option{'' if count == 1 else 's'} for "
                message = intro + ", ".join(preferences) + ". Choose one or tell me what to refine."
                if not response.products:
                    # Name every active filter, so a kept preference is never hidden.
                    hint = "say ‘any colour’ or" if intent.get("colour") else "try"
                    message = (
                        f"No {'more ' if info['more'] else ''}matches for "
                        + ", ".join(preferences)
                        + f". Change a filter (for example {hint} a new budget) "
                        "or choose New search."
                    )
                    if intent.get("size") is not None:
                        message += (
                            " Sizes are recorded for very few products here, so a size filter "
                            "often finds nothing. Say ‘any size’ to remove it."
                        )
                response = response.model_copy(update={"response_text": message})
            elif info["text"]:
                response = response.model_copy(update={"response_text": info["text"]})
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

    return workflow.state.record_turn(session_id, request, context, key, handle, shopping=True)
