"""Execute a conversational model's bounded read-only plan through owner contracts."""

import re
from dataclasses import replace
from time import monotonic

from shared.contracts.shopping import ShoppingMemory

from .intent import IntentResult, blank_intent, extract_intent, validate_constraints
from .intent_fallback import ModelFailure
from .shopping import QUESTIONS
from .shopping_llm import PROMPT_REVISION, TURN_SECONDS

RESPONSES = {
    "greeting": "Hello! Tell me what you're shopping for, including any colour or budget.",
    "thanks": "You're welcome! You can refine these choices or ask about a product.",
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
}


def provider_error_text(code, usage):
    status = (usage or {}).get("http_status")
    if status == 429:
        return "AI chat reached its usage limit. Please try again later."
    if status in {500, 502, 503, 504}:
        return (
            "AI chat is busy. Please try again shortly."
        )
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


def merged_intent(arguments, memory, text, dictionary):
    """Omitted fields preserve hard filters; every value still needs M2 vocabulary."""
    reset = getattr(arguments, "new_search", False)
    if reset and not re.search(r"\b(new|fresh|reset|start|over|forget|clear)\b", text, re.I):
        raise ModelFailure("MODEL_CONSTRAINT_CHANGED")
    intent = dict(memory.intent) if memory.intent and not reset else blank_intent("")
    changes = arguments.filters.model_dump(exclude_unset=True)
    # A disappearing constraint needs an explicit removal, never an omitted model field.
    for field, value in changes.items():
        previous = intent.get(field)
        if value is not None and previous is not None and value != previous:
            if field == "max_price_minor":
                mentioned = bool(re.search(r"\d", text)) or getattr(arguments, "cheaper", False)
            else:
                mentioned = str(value).casefold() in text.casefold()
            if not mentioned:
                raise ModelFailure("MODEL_CONSTRAINT_CHANGED")
        if value is None and intent.get(field) is not None:
            names = {"colour": "colou?r", "max_price_minor": "budget|price|limit"}
            if not re.search(
                r"\b(any|all|no|remove|clear|ignore|forget|don't|do not|doesn't|does not)\b",
                text,
                re.I,
            ) or not re.search(names.get(field, field), text, re.I):
                raise ModelFailure("MODEL_CONSTRAINT_CHANGED")
    intent.update(changes)
    if getattr(arguments, "more", False) and memory.intent and not reset:
        intent["query_text"] = memory.intent["query_text"]
    elif arguments.query.strip():
        intent["query_text"] = arguments.query.strip()
    # Check the unambiguous rule-extracted explicit filters as an independent guard.
    explicit = extract_intent(text, None, dictionary)
    for field in ("colour", "material", "size", "brand", "max_price_minor"):
        value = explicit.intent.get(field)
        if value is not None and field not in explicit.missing_fields:
            if field == "max_price_minor":
                # The rules preserve strict "under" boundaries; the model uses whole rupees.
                model_value = intent.get(field)
                if model_value is not None and model_value not in {value, value + 1}:
                    raise ModelFailure("MODEL_CONSTRAINT_CHANGED")
            elif field in changes and changes[field] != value:
                raise ModelFailure("MODEL_CONSTRAINT_CHANGED")
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
                    intent = merged_intent(args, memory, text, dictionary)
                    info["intent"] = intent
                    if args.new_search:
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
                        if issue:
                            info["pending"], info["text"] = [issue], QUESTIONS[issue]
                            return IntentResult(
                                outcome="clarification_required",
                                intent=intent,
                                missing_fields=[issue],
                                reason_code="UNRESOLVED_CONSTRAINT",
                                extractor_version=PROMPT_REVISION,
                                extractor_source="llm",
                                llm_call_count=1,
                                llm_ms=llm_ms,
                                model_usage=usage,
                            )
                        anchor = product_reference(memory, args.reference)
                        if args.reference is not None or body.selected_sku:
                            if anchor is None:
                                raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
                            info["selected"] = anchor["sku"]
                            # Retain the product subject instead of using unrelated title keywords.
                            if not intent["query_text"]:
                                intent["query_text"] = anchor["title"]
                        if args.cheaper:
                            choices = [anchor] if anchor else memory.products
                            prices = [
                                p["price_minor"]
                                for p in choices
                                if type(p.get("price_minor")) is int
                            ]
                            if not prices:
                                raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
                            intent["max_price_minor"] = min(
                                min(prices) - 1,
                                intent["max_price_minor"]
                                if intent["max_price_minor"] is not None
                                else 2**63 - 1,
                            )
                        more = args.more or anchor is not None
                        if more:
                            if len(memory.seen_skus) >= 200:
                                raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
                            options["exclude_skus"] = list(
                                dict.fromkeys(
                                    memory.seen_skus + ([anchor["sku"]] if anchor else [])
                                )
                            )[:200]
                        if not intent["query_text"].strip():
                            raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
                        info["search"], info["more"] = True, more
                elif plan.name == "product_details":
                    descriptions = []
                    for rank in dict.fromkeys(args.references):
                        product = product_reference(memory, rank)
                        if product is None:
                            raise ModelFailure("MODEL_UNSUPPORTED_INTENT")
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
                intro = f"I found {len(response.products)} {more_label}options for "
                message = intro + ", ".join(preferences) + ". Choose one or tell me what to refine."
                if not response.products:
                    message = (
                        "No matches with these preferences. Would you like to change a filter?"
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
