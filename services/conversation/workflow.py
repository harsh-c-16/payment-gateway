"""Fixed-mode workflow, provider facts, and crash-safe mutation delegation.

Only M1 tables are accessed. The journal is not an outbox or a saga: Orders
owns acceptance, stock/payment work, quote deduplication and finality.
"""

import asyncio
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from shared.contracts.common import ErrorCode, IdempotencyKey, RequestContext, UUIDText
from shared.contracts.conversation import TurnResponse, TurnTimings

from .clients import DependencyUnavailable, RemoteError
from .errors import ServiceError
from .intent import blank_intent, extract_intent, validate_constraints
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


class FixedWorkflow:
    def __init__(self, state, gateway, *, clock=None):
        self.state, self.gateway = state, gateway
        self.mode = gateway.mode
        if clock is not None and self.mode != "stub":
            raise ValueError("a test clock requires explicit stub mode")
        self.clock = clock or (lambda: datetime.now(UTC))

    def ready(self):
        self.gateway.ready()

    def call(self, name, context, **kwargs):
        return asyncio.run(self.gateway.call(name, context, **kwargs))

    def dispatch_turn(self, session_id, request, context, key):
        started = monotonic()
        return self.state.record_turn(
            session_id,
            request,
            context,
            key,
            lambda body, ctx: self._turn(body, ctx, key, started),
        )

    def _turn(self, request, context, key, started):
        parse_ms, search_ms, compose_ms = 0.0, 0.0, 0.0
        intent, search, products = None, None, []
        outcome, source = "clarification", "clarification"
        text = "Use the explicit cart, quote, checkout or status control."
        stage = monotonic()
        try:
            deadline = started + 3.0
            dictionary = self.call(
                "facets", context, deadline=deadline, params={"namespace": context.namespace}
            )
            result = extract_intent(request.text, context, dictionary)
            parse_ms = (monotonic() - stage) * 1000
            intent, source = result.intent, result.extractor_source
            if result.outcome != "valid":
                text = "Please clarify: " + ", ".join(result.missing_fields) + "."
            else:
                stage = monotonic()
                try:
                    search = self._search(intent, dictionary, context, key, deadline)
                finally:
                    search_ms = (monotonic() - stage) * 1000
                products, outcome = search["hits"], "success"
                stage = monotonic()
                text = compose_response(intent, search)
                compose_ms = (monotonic() - stage) * 1000
        except (DependencyUnavailable, RemoteError, ContractUnavailable, ContractViolation):
            if not parse_ms:
                parse_ms = (monotonic() - stage) * 1000
            outcome, text, products, search = (
                "dependency_error",
                "Catalogue unavailable; results are unknown. Retry later.",
                [],
                None,
            )
        return TurnResponse(
            turn_id=str(uuid4()),
            response_text=text,
            intent=intent,
            search_id=search["search_id"] if search else None,
            products=products,
            proposed_action=None,
            outcome=outcome,
            extractor_source=source,
            llm_call_count=0,
            timings_ms=TurnTimings(
                parse=parse_ms,
                llm=None,
                search=search_ms,
                compose=compose_ms,
                total=(monotonic() - started) * 1000,
            ),
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

    def _search(self, intent, dictionary, context, key, deadline):
        request = {
            "request_id": context.request_id,
            "session_id": context.session_id,
            "intent": intent,
            "top_k": 5,
            "mode": "lexical",
        }
        result = self.call("search", context, body=request, key=key, deadline=deadline)
        if (
            result["mode"] != "lexical"
            or result["embedding_calls"] != 0
            or result["returned_count"] != len(result["hits"])
            or len(result["hits"]) > request["top_k"]
            or result["returned_count"] > result["eligible_count"]
            or result["eligible_count"] > result["candidate_count"]
        ):
            raise ContractViolation("fixed search response mode/count mismatch")
        for hit in result["hits"]:
            if hit["dataset_revision"] != dictionary["dataset_revision"]:
                raise ContractViolation("search/dictionary revision mismatch")
            for field in ("category", "size", "colour", "material", "brand"):
                if intent.get(field) is not None and hit[field] != intent[field]:
                    raise ContractViolation("provider violated explicit hard filter")
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

    def checkout_cart(self, cart_id, request, context, key):
        return self._mutate("checkout_cart", cart_id, request, context, key)

    def _mutate(self, operation, cart_id, request, context, key):
        request = type(request).model_validate(request.model_dump(mode="json"))
        cart_id = TypeAdapter(UUIDText).validate_python(cart_id)
        scope = self._scope(context, operation, key)
        business = {"cart_id": cart_id, **request.model_dump(mode="json")}
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
        name = "quote" if operation == "request_quote" else "order_create"
        try:
            result = self.call(
                name,
                RequestContext.model_validate(command["provider_context"]),
                body=command["provider_input"],
                key=command["remote_key"],
                deadline=monotonic() + 2,
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
