"""Fixed-mode workflow, provider facts, and crash-safe mutation delegation.

Only M1 tables are accessed. The journal is not an outbox or a saga: Orders
owns acceptance, stock/payment work, quote deduplication and finality.
"""

import asyncio
import hashlib
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from shared.contracts.common import ErrorCode, IdempotencyKey, RequestContext, UUIDText
from shared.contracts.conversation import TurnResponse, TurnTimings
from shared.telemetry.metrics import Telemetry

from .clients import DependencyUnavailable, RemoteError
from .errors import ServiceError
from .intent import blank_intent, canonical_text, extract_intent, validate_constraints
from .intent_fallback import REASON_CODES, OpenAIIntentProvider, eligible, fallback, output_schema
from .provider_contracts import ENDPOINTS, ContractUnavailable, ContractViolation
from .state import canonical_hash, conflict


def dependency(*, unknown=False):
    return ServiceError(
        503,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "Dependency unavailable. Retry with the same operation identity.",
        details={"outcome": "unknown" if unknown else "unavailable", "retry": "same_key"},
    )


def compose_response(intent=None, search_response=None, action_status=None):
    """Templates use supplied facts only; text is never parsed back into commands."""
    if action_status is not None:
        if "total_amount_minor" in action_status:
            return (
                f"Quote {action_status['quote_id']}: {action_status['currency']} "
                f"{action_status['total_amount_minor']} minor units. "
                "Confirm this quote and cart version using the checkout control."
            )
        return f"Order {action_status['order_id']}: {action_status['status']}."
    if not search_response or not search_response["hits"]:
        return "No products match these constraints. No filters were relaxed."
    return "\n".join(
        f"{hit['title']} | SKU {hit['sku']} | {hit['currency']} {hit['price_minor']} minor units "
        f"| size {hit['size'] if hit['size'] is not None else 'unknown'} "
        f"| displayed availability {hit['stock_available']} (rechecked at checkout)"
        for hit in search_response["hits"]
    )


@dataclass(frozen=True)
class TurnExecution:
    response: TurnResponse
    diagnostic: dict
    event_facts: tuple = ()
    rejection_diagnostic: dict | None = None
    rejected_output: str | None = dataclass_field(default=None, repr=False)
    shopping_context: dict | None = None

    def model_dump(self, **kwargs):
        return self.response.model_dump(**kwargs)


class FixedWorkflow:
    def __init__(
        self,
        state,
        gateway,
        *,
        clock=None,
        assistant_mode="fixed",
        allow_intent_llm=False,
        intent_provider=None,
    ):
        self.state, self.gateway = state, gateway
        self.mode = gateway.mode
        if clock is not None and self.mode != "stub":
            raise ValueError("a test clock requires explicit stub mode")
        self.clock = clock or (lambda: datetime.now(UTC))
        if assistant_mode not in {"fixed", "assist"} or type(allow_intent_llm) is not bool:
            raise ValueError("explicit fixed/assist policy required")
        if assistant_mode == "fixed" and allow_intent_llm:
            raise ValueError("fixed mode cannot enable generative calls")
        if intent_provider is not None and (
            intent_provider.mode != self.mode
            or (self.mode == "real" and type(intent_provider) is not OpenAIIntentProvider)
        ):
            raise ValueError("real workflow requires the single-HTTP-attempt model provider")
        self.assistant_mode, self.allow_intent_llm = assistant_mode, allow_intent_llm
        self.intent_provider = intent_provider
        self.telemetry = Telemetry(
            label_values={
                "outcome": {"success", "failure"},
                "mode": {"fixed", "assist"},
                "reason": REASON_CODES,
            }
        )

    def ready(self):
        self.gateway.ready()

    def call(self, name, context, *, turn_tools=None, **kwargs):
        started, outcome = monotonic(), "failure"
        try:
            result = asyncio.run(self.gateway.call(name, context, **kwargs))
            outcome = "success"
            return result
        finally:
            if turn_tools is not None:
                turn_tools.append(
                    {
                        "tool_call_id": str(uuid4()),
                        "tool_name": name,
                        "outcome": outcome,
                        "duration_ms": (monotonic() - started) * 1000,
                        "event_time": self.clock(),
                    }
                )

    def dispatch_turn(self, session_id, request, context, key):
        started = monotonic()
        return self.state.record_turn(
            session_id,
            request,
            context,
            key,
            lambda body, ctx: self._turn(body, ctx, key, started),
        )

    def _turn(
        self,
        request,
        context,
        key,
        started,
        *,
        prepare=None,
        search_options=None,
        deadline_seconds=3.0,
        intent_fallback=True,
        model_config=None,
        prepared_tools=None,
    ):
        turn_tools = prepared_tools if prepared_tools is not None else []
        parse_ms, search_ms, compose_ms = 0.0, 0.0, 0.0
        intent, search, products = None, None, []
        outcome, source = "clarification", "clarification"
        text = "Use the explicit cart, quote, checkout or status control."
        stage = monotonic()
        result, dictionary, reused_attempt = None, None, False
        intent_at = None
        attempt_config = None
        try:
            deadline = started + deadline_seconds
            dictionary = self.call(
                "facets",
                context,
                deadline=deadline,
                params={"namespace": context.namespace},
                turn_tools=turn_tools,
            )
            if self.state is not None:
                self.state.events.check_revision(dictionary["dataset_revision"])
            result = (
                prepare(request.text, dictionary)
                if prepare is not None
                else extract_intent(request.text, context, dictionary)
            )
            parse_ms = (monotonic() - stage) * 1000
            if not intent_fallback and result.llm_ms is not None:
                parse_ms = max(0.0, parse_ms - result.llm_ms)
            if intent_fallback and request.mode == "assist" and eligible(result, request.text):
                if self.assistant_mode == "assist" and self.allow_intent_llm:
                    if self.intent_provider is not None and monotonic() < deadline:
                        reservation = self.state.claim_intent_attempt(
                            request,
                            context,
                            {
                                **self.intent_provider.settings.provenance(),
                                "schema_sha256": canonical_hash(output_schema(dictionary)),
                                "dictionary_version": dictionary["dictionary_version"],
                            },
                        )
                        attempt_config = reservation["provider_config"]
                        if not reservation["claimed"]:
                            reused_attempt = True
                            result = replace(
                                result,
                                reason_code="MODEL_PREVIOUS_ATTEMPT",
                                llm_call_count=1,
                                llm_ms=None,
                            )
                    if not reused_attempt:
                        result = asyncio.run(
                            fallback(
                                result,
                                request.text,
                                dictionary,
                                self.intent_provider,
                                deadline=deadline,
                            )
                        )
                else:
                    result = replace(result, reason_code="MODEL_DISABLED")
            intent_at = self.clock()
            intent, source = result.intent, result.extractor_source
            if result.outcome != "valid":
                text = "Please clarify: " + ", ".join(result.missing_fields) + "."
            else:
                stage = monotonic()
                try:
                    search = self._search(
                        intent,
                        dictionary,
                        context,
                        key,
                        deadline,
                        turn_tools=turn_tools,
                        **(search_options or {}),
                    )
                finally:
                    search_ms = (monotonic() - stage) * 1000
                products, outcome = search["hits"], "success"
                stage = monotonic()
                text = compose_response(intent, search)
                compose_ms = (monotonic() - stage) * 1000
        except (DependencyUnavailable, RemoteError, ContractUnavailable, ContractViolation):
            if turn_tools:
                turn_tools[-1]["outcome"] = "failure"
            if not parse_ms:
                parse_ms = (monotonic() - stage) * 1000
            outcome, text, products, search = (
                "dependency_error",
                "Catalogue unavailable; results are unknown. Retry later.",
                [],
                None,
            )
        calls = result.llm_call_count if result else 0
        model_ms = result.llm_ms if result else None
        if calls and not reused_attempt:
            self.telemetry.record(
                "intent_llm_calls_total",
                calls,
                outcome="success" if result.extractor_source == "llm" else "failure",
            )
            if model_ms is not None:
                self.telemetry.record("intent_llm_duration_seconds", model_ms / 1000)
        response = TurnResponse(
            turn_id=str(uuid4()),
            response_text=text,
            intent=intent,
            search_id=search["search_id"] if search else None,
            products=products,
            proposed_action=None,
            outcome=outcome,
            extractor_source=source,
            llm_call_count=calls,
            timings_ms=TurnTimings(
                parse=parse_ms,
                llm=model_ms,
                search=search_ms,
                compose=compose_ms,
                total=(monotonic() - started) * 1000,
            ),
        )
        diagnostic = {
            "mode": request.mode,
            "configured_mode": self.assistant_mode,
            "test_mode": self.mode,
            "reason_code": result.reason_code if result else "CATALOG_UNAVAILABLE",
            "model_attempts": calls,
            "reused_attempt_reservation": reused_attempt,
            "model_ms": model_ms,
            "model_usage": result.model_usage if result else None,
            "model_cost": None,
            "model_settings": (attempt_config or model_config) if calls else None,
            "dictionary_version": dictionary["dictionary_version"] if dictionary else None,
            "deterministic_extractor_version": result.extractor_version if result else None,
            "query_embedding_calls": search["embedding_calls"] if search else None,
            "query_embedding_ms": search.get("timings_ms", {}).get("embedding") if search else None,
        }
        if calls and not reused_attempt:
            self.state.complete_intent_attempt(context, diagnostic)
        elapsed = monotonic() - started
        response = response.model_copy(
            update={"timings_ms": response.timings_ms.model_copy(update={"total": elapsed * 1000})}
        )
        if elapsed >= deadline_seconds:
            response = response.model_copy(
                update={
                    "outcome": "dependency_error",
                    "products": [],
                    "search_id": None,
                    "response_text": "Turn deadline exceeded; results are unknown. Retry later.",
                }
            )
        self.telemetry.record("turn_duration_seconds", elapsed, mode=request.mode)
        if response.outcome == "clarification":
            self.telemetry.record("intent_clarifications_total", 1, reason=result.reason_code)
        facts = [
            {
                "event_type": "TOOL_CALLED",
                "event_time": tool["event_time"],
                "payload": {
                    "turn_id": response.turn_id,
                    **{key: value for key, value in tool.items() if key != "event_time"},
                },
            }
            for tool in turn_tools
        ]
        rejection = None
        if result is not None:
            payload = {"turn_id": response.turn_id, "extractor_version": result.extractor_version}
            if result.outcome == "valid":
                facts.append(
                    {
                        "event_type": "INTENT_EXTRACTED",
                        "event_time": intent_at,
                        "payload": {**payload, "intent": result.intent, "outcome": "valid"},
                    }
                )
            else:
                reference = "m1-turn:" + response.turn_id
                facts.append(
                    {
                        "event_type": "INTENT_REJECTED",
                        "event_time": intent_at,
                        "payload": {
                            **payload,
                            "reason_code": result.reason_code,
                            "restricted_content_reference": reference,
                        },
                    }
                )
                if result.reason_code == "MODEL_INVALID_OUTPUT":
                    rejection = {
                        "diagnostic_id": str(uuid4()),
                        "namespace": context.namespace,
                        "run_id": context.run_id,
                        "source_service": "conversation",
                        "reason_code": "MODEL_OUTPUT_INVALID",
                        "correlation_id": context.correlation_id,
                        "created_at": self.clock(),
                        "content_hash": (
                            hashlib.sha256(result.rejected_output.encode("utf-8")).hexdigest()
                            if result.rejected_output is not None
                            else canonical_hash(diagnostic)
                        ),
                        "restricted_content_reference": reference,
                        "source_coordinates": None,
                    }
        return TurnExecution(
            response,
            diagnostic,
            tuple(facts),
            rejection,
            result.rejected_output if result is not None else None,
        )

    def structured_search(self, intent, context, *, key):
        """Python adapter for controls; HTTP structured search is M2 /v1/search.

        The frozen M1 TurnRequest has no structured field. Do not add an
        unreviewed endpoint or smuggle a structured object into text.
        """
        deadline = monotonic() + 3
        dictionary = self.call(
            "facets", context, deadline=deadline, params={"namespace": context.namespace}
        )
        intent = {**blank_intent(""), **intent}
        issue = validate_constraints(intent, dictionary)
        if issue:
            raise ServiceError(
                422,
                ErrorCode.UNSUPPORTED_FILTER,
                "Unsupported structured filter.",
                details={"field": issue},
            )
        return self._search(intent, dictionary, context, key, deadline)

    def _search(
        self,
        intent,
        dictionary,
        context,
        key,
        deadline,
        *,
        turn_tools=None,
        mode="lexical",
        exclude_skus=(),
        top_k=5,
    ):
        request = {
            "request_id": context.request_id,
            "session_id": context.session_id,
            "intent": intent,
            "top_k": top_k,
            "mode": mode,
        }
        if exclude_skus:
            request["exclude_skus"] = list(exclude_skus)
        result = self.call(
            "search", context, body=request, key=key, deadline=deadline, turn_tools=turn_tools
        )
        semantic_query = mode in {"vector_exact", "hybrid_exact", "hybrid_ann"} and any(
            (intent.get(field) or "").strip() for field in ("query_text", "occasion")
        )
        if (
            result["mode"] != mode
            or result["embedding_calls"] not in ({0} if mode == "lexical" else {0, 1})
            or result["returned_count"] != len(result["hits"])
            or len(result["hits"]) > request["top_k"]
            or result["returned_count"] > result["eligible_count"]
            or result["eligible_count"] > result["candidate_count"]
            or len({hit["sku"] for hit in result["hits"]}) != len(result["hits"])
            or (
                semantic_query
                and (result["embedding_calls"] != 1 or not result["embedding_revision"])
            )
        ):
            raise ContractViolation("fixed search response mode/count mismatch")
        for rank, hit in enumerate(result["hits"], 1):
            if hit["sku"] in exclude_skus:
                raise ContractViolation("provider repeated an explicitly excluded product")
            if hit["retrieval_mode"] != mode or hit["rank"] != rank or hit["stock_available"] <= 0:
                raise ContractViolation("search hit rank/availability mismatch")
            if hit["dataset_revision"] != dictionary["dataset_revision"]:
                raise ContractViolation("search/dictionary revision mismatch")
            for field in ("category", "size", "colour", "material"):
                if intent.get(field) is not None and hit[field] != intent[field]:
                    raise ContractViolation("provider violated explicit hard filter")
            if intent.get("brand") is not None and (
                hit["brand"] is None or canonical_text(hit["brand"]) != intent["brand"]
            ):
                raise ContractViolation("provider violated explicit brand filter")
            if (
                intent["max_price_minor"] is not None
                and hit["price_minor"] > intent["max_price_minor"]
            ):
                raise ContractViolation("provider violated price bound")
        return result

    def order_status(self, order_id, context):
        order_id = TypeAdapter(UUIDText).validate_python(order_id)
        try:
            result = self.call("order_status", context, order_id=order_id, deadline=monotonic() + 2)
        except (DependencyUnavailable, ContractUnavailable, ContractViolation) as exc:
            raise dependency() from exc
        except RemoteError as exc:
            raise self.remote_error(exc) from exc
        if result["order_id"] != order_id or result["user_id"] != context.user_id:
            raise dependency()
        if context.session_id is not None and result["session_id"] != context.session_id:
            raise dependency()
        return result

    @staticmethod
    def remote_error(exc, *, unknown=False):
        if exc.status == 503:
            return dependency(unknown=unknown)
        return ServiceError(
            exc.status,
            exc.payload.error.code,
            "Provider rejected the operation.",
            details={"source": "provider"},
        )

    def _scope(self, context, operation, key):
        return (
            context.namespace,
            context.user_id,
            operation,
            TypeAdapter(IdempotencyKey).validate_python(key),
        )

    def _command(self, tx, scope):
        return tx.execute(
            "SELECT * FROM workflow_commands WHERE namespace=%s AND user_id=%s "
            "AND operation=%s AND key=%s",
            scope,
        ).fetchone()

    def _result(self, command):
        if command["state"] == "rejected":
            error = command["error"]
            raise ServiceError(error["status"], error["code"], "Provider rejected the operation.")
        return command["response"]

    def request_quote(self, cart_id, request, context, key):
        return self._mutate("request_quote", cart_id, request, context, key)

    def checkout_cart(self, cart_id, request, context, key, *, benchmark_headers=None):
        return self._mutate(
            "checkout_cart", cart_id, request, context, key, benchmark_headers=benchmark_headers
        )

    def _mutate(self, operation, cart_id, request, context, key, *, benchmark_headers=None):
        request = type(request).model_validate(request.model_dump(mode="json"))
        cart_id = TypeAdapter(UUIDText).validate_python(cart_id)
        scope = self._scope(context, operation, key)
        business = {"cart_id": cart_id, **request.model_dump(mode="json")}
        if benchmark_headers:
            business["benchmark_headers"] = benchmark_headers
        digest = canonical_hash(business)
        # Commit stable downstream identity and confirmation BEFORE the remote call.
        with self.state.database.transaction() as tx:
            self.state._lock(tx, scope)
            row = self.state._cart(tx, cart_id, context, lock=True)
            command = self._command(tx, scope)
            if command:
                if command["request_hash"] != digest:
                    raise conflict()
                cached = self._result(command)
                if cached is not None:
                    return cached
            else:
                # Fail before journalling or contacting a mutation provider if
                # the required event path cannot be initialized.
                self.state.events.ready()
                if row["version"] != request.expected_cart_version:
                    raise conflict(ErrorCode.CART_VERSION_CONFLICT)
                if operation == "request_quote":
                    self.state.check_pending_checkout(tx, row)
                    cart = self.state._snapshot(tx, row)
                    if not cart.lines:
                        raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Cart is empty.")
                    provider_input = {
                        "cart_id": cart_id,
                        "cart_version": row["version"],
                        "lines": [x.model_dump(mode="json") for x in cart.lines],
                    }
                    remote_key = "m1-quote-" + canonical_hash(scope)
                else:
                    if (
                        row["quote_id"] is None
                        or str(row["quote_id"]) != request.quote_id
                        or row["quote_cart_version"] != row["version"]
                    ):
                        raise conflict(ErrorCode.CART_VERSION_CONFLICT)
                    if (
                        row["confirmation_id"] is not None
                        and str(row["confirmation_id"]) != request.confirmation_id
                    ):
                        raise conflict()
                    # Existing accepted/pending quote retries remain recoverable after expiry.
                    if row["confirmation_id"] is None:
                        quote = row["quote_payload"]
                        if (
                            not quote
                            or datetime.fromisoformat(quote["expires_at"].replace("Z", "+00:00"))
                            <= self.clock()
                        ):
                            raise conflict(ErrorCode.QUOTE_EXPIRED)
                    tx.execute(
                        "INSERT INTO confirmations (namespace,user_id,confirmation_id,"
                        "cart_id,quote_id,cart_version) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        (
                            context.namespace,
                            context.user_id,
                            request.confirmation_id,
                            cart_id,
                            request.quote_id,
                            row["version"],
                        ),
                    )
                    confirmation = tx.execute(
                        "SELECT cart_id,quote_id,cart_version FROM confirmations "
                        "WHERE namespace=%s AND user_id=%s AND confirmation_id=%s",
                        (context.namespace, context.user_id, request.confirmation_id),
                    ).fetchone()
                    if (
                        str(confirmation["cart_id"]) != cart_id
                        or str(confirmation["quote_id"]) != request.quote_id
                        or confirmation["cart_version"] != row["version"]
                    ):
                        raise conflict()
                    tx.execute(
                        "UPDATE carts SET confirmation_id=%s WHERE namespace=%s AND cart_id=%s",
                        (request.confirmation_id, context.namespace, cart_id),
                    )
                    provider_input = {
                        "quote_id": request.quote_id,
                        "session_id": str(row["session_id"]),
                        "confirmation_id": request.confirmation_id,
                    }
                    remote_key = "m1-checkout-" + canonical_hash(
                        (context.namespace, context.user_id, request.quote_id)
                    )
                provider_context = context.model_copy(update={"session_id": str(row["session_id"])})
                tx.execute(
                    "INSERT INTO workflow_commands (namespace,user_id,operation,key,cart_id,"
                    "request_hash,business_input,provider_input,provider_context,remote_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        *scope,
                        cart_id,
                        digest,
                        Jsonb(business),
                        Jsonb(provider_input),
                        Jsonb(provider_context.model_dump(mode="json")),
                        remote_key,
                    ),
                )
                command = self._command(tx, scope)
            if operation == "checkout_cart":
                accepted = tx.execute(
                    "SELECT response FROM workflow_commands WHERE namespace=%s AND user_id=%s "
                    "AND operation=%s AND remote_key=%s AND state='complete' LIMIT 1",
                    (*scope[:3], command["remote_key"]),
                ).fetchone()
                if accepted is not None:
                    # A new transport key aliases an already accepted quote. Replay
                    # our durable acceptance even if Orders is down or has finalized.
                    tx.execute(
                        "UPDATE workflow_commands SET state='complete',response=%s "
                        "WHERE namespace=%s AND user_id=%s AND operation=%s AND remote_key=%s "
                        "AND state='pending'",
                        (Jsonb(accepted["response"]), *scope[:3], command["remote_key"]),
                    )
                    return accepted["response"]
        name = "quote" if operation == "request_quote" else "order_create"
        try:
            extra = command["business_input"].get("benchmark_headers")
            result = self.call(
                name,
                RequestContext.model_validate(command["provider_context"]),
                body=command["provider_input"],
                key=command["remote_key"],
                deadline=monotonic() + 2,
                **({"headers": extra} if extra else {}),
            )
            self._validate_result(name, result, command)
        except RemoteError as exc:
            if 400 <= exc.status < 500 and exc.status != 429:
                with self.state.database.transaction() as tx:
                    self.state._cart(tx, cart_id, context, lock=True)
                    tx.execute(
                        "UPDATE workflow_commands SET state='rejected',error=%s "
                        "WHERE namespace=%s AND user_id=%s AND operation=%s AND remote_key=%s "
                        "AND state='pending'",
                        (
                            Jsonb({"status": exc.status, "code": exc.payload.error.code.value}),
                            *scope[:3],
                            command["remote_key"],
                        ),
                    )
            raise self.remote_error(exc, unknown=True) from exc
        except (DependencyUnavailable, ContractViolation, ContractUnavailable) as exc:
            raise dependency(unknown=True) from exc
        with self.state.database.transaction() as tx:
            row = self.state._cart(tx, cart_id, context, lock=True)
            current = self._command(tx, scope)
            cached = self._result(current)
            if cached is not None:
                if name == "order_create" and cached["order_id"] != result["order_id"]:
                    raise dependency(unknown=True)
                return cached
            if name == "quote":
                if row["version"] != request.expected_cart_version:
                    raise conflict(ErrorCode.CART_VERSION_CONFLICT)
                self.state.check_pending_checkout(tx, row)
                tx.execute(
                    "UPDATE carts SET quote_id=%s,quote_cart_version=%s,confirmation_id=NULL,"
                    "quote_payload=%s WHERE namespace=%s AND cart_id=%s",
                    (result["quote_id"], row["version"], Jsonb(result), context.namespace, cart_id),
                )
            else:
                # A fresh HTTP key for this same quote still addresses the same
                # downstream operation. The session lock serializes first acceptance.
                accepted = tx.execute(
                    "SELECT response FROM workflow_commands WHERE namespace=%s AND user_id=%s "
                    "AND operation=%s AND remote_key=%s AND state='complete' LIMIT 1",
                    (*scope[:3], command["remote_key"]),
                ).fetchone()
                if accepted is None:
                    accepted_context = RequestContext.model_validate(command["provider_context"])
                    self.state._event(
                        tx,
                        row,
                        accepted_context,
                        "CHECKOUT_STARTED",
                        {
                            "cart_id": cart_id,
                            "quote_id": command["provider_input"]["quote_id"],
                            "order_id": result["order_id"],
                            "confirmation_id": command["provider_input"]["confirmation_id"],
                        },
                        self.clock(),
                    )
                else:
                    if accepted["response"]["order_id"] != result["order_id"]:
                        raise dependency(unknown=True)
                    # Another alias completed while this HTTP call was in flight.
                    # Status may advance; the accepted order identity must not.
                    result = accepted["response"]
            tx.execute(
                "UPDATE workflow_commands SET state='complete',response=%s "
                "WHERE namespace=%s AND user_id=%s AND operation=%s AND remote_key=%s "
                "AND state='pending'",
                (Jsonb(result), *scope[:3], command["remote_key"]),
            )
        return result

    def _validate_result(self, name, result, command):
        # The gateway validates the canonical owner schema; these are M1 bindings.
        self.gateway.contracts.validate(ENDPOINTS[name], "response", result)
        if name == "quote":
            expected = command["provider_input"]
            if any(result[f] != expected[f] for f in ("cart_id", "cart_version")):
                raise ContractViolation("quote/cart mismatch")
            if result["user_id"] != command["user_id"]:
                raise ContractViolation("quote/principal mismatch")
            wanted = {x["sku"]: x["quantity"] for x in expected["lines"]}
            actual = {x["sku"]: x["quantity"] for x in result["lines"]}
            if wanted != actual or len(actual) != len(result["lines"]):
                raise ContractViolation("quote lines mismatch")
            # Never compute/replace the authoritative total in M1.
        elif result["status_url"] != "/v1/orders/" + result["order_id"]:
            raise ContractViolation("unexpected order status URL")
