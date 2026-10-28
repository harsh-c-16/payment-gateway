"""Durable M1 state. Every effect, result and shared outbox append commits together."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from shared.contracts.common import (
    INT64_MAX,
    ErrorCode,
    IdempotencyKey,
    RequestContext,
    Sku,
    UUIDText,
)
from shared.contracts.conversation import (
    CartSnapshot,
    CartUpdateRequest,
    SessionCreated,
    TurnRequest,
    TurnResponse,
)

from .database import Database
from .errors import ServiceError
from .events import SharedEvents


class TurnHandler(Protocol):
    """P7 supplies workflow + canonical nested-provider validation, outside P6."""

    def __call__(self, request: TurnRequest, context: RequestContext) -> TurnResponse: ...


def canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def conflict(code=ErrorCode.IDEMPOTENCY_CONFLICT):
    return ServiceError(409, code, "Request conflicts with durable conversation state.")


class ConversationState:
    def __init__(self, database: Database, *, events=None):
        self.database = database
        self.events = events if events is not None else SharedEvents()

    def ready(self):
        self.database.ready()
        self.events.ready()

    def _lock(self, tx, values):
        # Transaction-scoped lock: serializes even the first request for a new key.
        # Hash collisions only serialize unrelated operations; identity remains SQL-keyed.
        key = int.from_bytes(bytes.fromhex(canonical_hash(values))[:8], signed=True)
        tx.execute("SELECT pg_advisory_xact_lock(%s)", (key,))

    def _operation(self, tx, context, operation, key, business_input):
        key = TypeAdapter(IdempotencyKey).validate_python(key)
        digest = canonical_hash(business_input)
        scope = (context.namespace, context.user_id, operation, key)
        self._lock(tx, scope)
        row = tx.execute(
            "SELECT request_hash, response FROM operation_keys "
            "WHERE namespace=%s AND user_id=%s AND operation=%s AND key=%s",
            scope,
        ).fetchone()
        if row and row["request_hash"] != digest:
            raise conflict()
        return scope, digest, row["response"] if row else None

    def _save(self, tx, scope, digest, response):
        tx.execute(
            "INSERT INTO operation_keys "
            "(namespace,user_id,operation,key,request_hash,response,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,clock_timestamp())",
            (*scope, digest, Jsonb(response.model_dump(mode="json"))),
        )

    def create_session(self, context: RequestContext, key: str) -> SessionCreated:
        with self.database.transaction() as tx:
            scope, digest, cached = self._operation(tx, context, "create_session", key, {})
            if cached is not None:
                return SessionCreated.model_validate(cached)
            session_id, cart_id = str(uuid4()), str(uuid4())
            tx.execute(
                "INSERT INTO sessions (namespace,session_id,user_id,created_at) "
                "VALUES (%s,%s,%s,clock_timestamp())",
                (context.namespace, session_id, context.user_id),
            )
            tx.execute(
                "INSERT INTO carts (namespace,cart_id,session_id,user_id,updated_at) "
                "VALUES (%s,%s,%s,%s,clock_timestamp())",
                (context.namespace, cart_id, session_id, context.user_id),
            )
            response = SessionCreated(session_id=session_id, cart_id=cart_id, cart_version=0)
            self._save(tx, scope, digest, response)
            # No SESSION_CREATED event exists in the canonical catalogue.
            return response

    def _cart(self, tx, cart_id, context, *, lock=False):
        # Session lock orders cart and turn events on the same aggregate stream.
        row = tx.execute(
            "SELECT c.* FROM carts c JOIN sessions s USING (namespace,session_id) "
            "WHERE c.namespace=%s AND c.cart_id=%s" + (" FOR UPDATE OF s,c" if lock else ""),
            (context.namespace, cart_id),
        ).fetchone()
        if not row:
            raise ServiceError(404, ErrorCode.NOT_FOUND, "Cart was not found.")
        if row["user_id"] != context.user_id:
            raise ServiceError(403, ErrorCode.FORBIDDEN, "Cart belongs to another principal.")
        if context.session_id is not None and context.session_id != str(row["session_id"]):
            raise ServiceError(403, ErrorCode.FORBIDDEN, "Session does not own this cart.")
        return row

    def _snapshot(self, tx, row):
        lines = tx.execute(
            "SELECT sku,quantity,display_price_minor FROM cart_items "
            "WHERE namespace=%s AND cart_id=%s ORDER BY sku",
            (row["namespace"], row["cart_id"]),
        ).fetchall()
        return CartSnapshot(
            cart_id=str(row["cart_id"]),
            session_id=str(row["session_id"]),
            user_id=row["user_id"],
            version=row["version"],
            lines=lines,
            updated_at=row["updated_at"],
        )

    def get_cart(self, cart_id: str, context: RequestContext) -> CartSnapshot:
        cart_id = TypeAdapter(UUIDText).validate_python(cart_id)
        with self.database.transaction() as tx:
            # A consistent read spans cart version and all lines. Writers hold this
            # same session/cart lock; READ COMMITTED alone could mix two versions.
            return self._snapshot(tx, self._cart(tx, cart_id, context, lock=True))

    def _event(self, tx, row, context, event_type, payload, occurred_at):
        version = tx.execute(
            "UPDATE sessions SET event_version=event_version+1 "
            "WHERE namespace=%s AND session_id=%s AND event_version<%s RETURNING event_version",
            (context.namespace, row["session_id"], INT64_MAX),
        ).fetchone()
        if not version:
            raise conflict(ErrorCode.ILLEGAL_STATE)
        self.events.append(
            tx,
            event_type=event_type,
            payload=payload,
            context=context.model_copy(update={"session_id": str(row["session_id"])}),
            version=version["event_version"],
            event_time=occurred_at,
        )

    def update_cart(self, cart_id, sku, request: CartUpdateRequest, context, key):
        cart_id = TypeAdapter(UUIDText).validate_python(cart_id)
        sku = TypeAdapter(Sku).validate_python(sku)
        business = {"cart_id": cart_id, "sku": sku, **request.model_dump(mode="json")}
        with self.database.transaction() as tx:
            scope, digest, cached = self._operation(tx, context, "update_cart", key, business)
            row = self._cart(tx, cart_id, context, lock=True)
            if cached is not None:
                return CartSnapshot.model_validate(cached)
            if request.expected_cart_version != row["version"]:
                raise conflict(ErrorCode.CART_VERSION_CONFLICT)
            self.check_pending_checkout(tx, row)
            if row["version"] == INT64_MAX:
                raise conflict(ErrorCode.ILLEGAL_STATE)
            self.events.ready()
            if request.quantity == 0:
                tx.execute(
                    "DELETE FROM cart_items WHERE namespace=%s AND cart_id=%s AND sku=%s",
                    (context.namespace, cart_id, sku),
                )
            else:
                items = tx.execute(
                    "SELECT sku FROM cart_items WHERE namespace=%s AND cart_id=%s",
                    (context.namespace, cart_id),
                ).fetchall()
                if len(items) >= 20 and sku not in {item["sku"] for item in items}:
                    raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Cart has 20 unique lines.")
                tx.execute(
                    "INSERT INTO cart_items (namespace,cart_id,sku,quantity) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (namespace,cart_id,sku) DO UPDATE SET quantity=EXCLUDED.quantity",
                    (context.namespace, cart_id, sku, request.quantity),
                )
            row = tx.execute(
                "UPDATE carts SET version=version+1,updated_at=clock_timestamp(),"
                "quote_id=NULL,quote_cart_version=NULL,confirmation_id=NULL,quote_payload=NULL "
                "WHERE namespace=%s AND cart_id=%s RETURNING *",
                (context.namespace, cart_id),
            ).fetchone()
            response = self._snapshot(tx, row)
            self._event(
                tx,
                row,
                context,
                "ADD_TO_CART",
                {
                    "cart_id": cart_id,
                    "cart_version": row["version"],
                    "sku": sku,
                    "quantity_after": request.quantity,
                },
                row["updated_at"],
            )
            self._save(tx, scope, digest, response)
            return response

    def check_pending_checkout(self, tx, row):
        pending = tx.execute(
            "SELECT 1 FROM workflow_commands WHERE namespace=%s AND cart_id=%s "
            "AND operation='checkout_cart' AND state='pending' LIMIT 1",
            (row["namespace"], row["cart_id"]),
        ).fetchone()
        if pending:
            raise ServiceError(
                409,
                ErrorCode.ILLEGAL_STATE,
                "Checkout outcome is unresolved; retry the original checkout before editing.",
            )

    def claim_intent_attempt(self, request, context, provider_config):
        """Reserve one provider attempt durably before I/O, even if the turn later rolls back."""
        digest = canonical_hash(
            {"session_id": context.session_id, **request.model_dump(mode="json")}
        )
        with self.database.transaction(intent_audit=True) as tx:
            claimed = tx.execute(
                "INSERT INTO intent_attempts "
                "(namespace,request_id,run_id,session_id,user_id,request_hash,provider_config) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING request_id",
                (
                    context.namespace,
                    request.request_id,
                    context.run_id,
                    context.session_id,
                    context.user_id,
                    digest,
                    Jsonb(provider_config),
                ),
            ).fetchone()
            if claimed:
                return {"claimed": True, "provider_config": provider_config}
            existing = tx.execute(
                "SELECT user_id,request_hash,provider_config FROM intent_attempts "
                "WHERE namespace=%s AND request_id=%s",
                (context.namespace, request.request_id),
            ).fetchone()
            if existing["user_id"] != context.user_id or existing["request_hash"] != digest:
                raise conflict()
            return {"claimed": False, "provider_config": existing["provider_config"]}

    def complete_intent_attempt(self, context, diagnostic):
        """Actual returned usage/error survives any later response/event rollback."""
        with self.database.transaction(intent_audit=True) as tx:
            tx.execute(
                "UPDATE intent_attempts SET diagnostic=%s WHERE namespace=%s AND request_id=%s "
                "AND user_id=%s AND diagnostic IS NULL",
                (Jsonb(diagnostic), context.namespace, context.request_id, context.user_id),
            )

    def record_turn(self, session_id, request: TurnRequest, context, key, handler: TurnHandler):
        """Persist a caller-supplied workflow outcome; P6 implements no workflow.

        The handler must validate provider JSON before returning. It must make no
        purchase mutation: purchase actions have their own explicit endpoints.
        """
        session_id = TypeAdapter(UUIDText).validate_python(session_id)
        if request.request_id != context.request_id:
            raise ServiceError(400, ErrorCode.BAD_REQUEST, "Body/header request IDs must match.")
        if context.session_id is not None and context.session_id != session_id:
            raise ServiceError(403, ErrorCode.FORBIDDEN, "Session context does not match path.")
        business = {"session_id": session_id, **request.model_dump(mode="json")}
        with self.database.transaction() as tx:
            scope, digest, cached = self._operation(tx, context, "submit_turn", key, business)
            self._lock(tx, (context.namespace, "turn_request", request.request_id))
            row = tx.execute(
                "SELECT * FROM sessions WHERE namespace=%s AND session_id=%s FOR UPDATE",
                (context.namespace, session_id),
            ).fetchone()
            if not row:
                raise ServiceError(404, ErrorCode.NOT_FOUND, "Session was not found.")
            if row["user_id"] != context.user_id:
                raise ServiceError(
                    403, ErrorCode.FORBIDDEN, "Session belongs to another principal."
                )
            if cached is not None:
                return TurnResponse.model_validate(cached)
            previous = tx.execute(
                "SELECT user_id,request_hash,response FROM turns "
                "WHERE namespace=%s AND request_id=%s",
                (context.namespace, request.request_id),
            ).fetchone()
            if previous:
                if previous["user_id"] != context.user_id or previous["request_hash"] != digest:
                    raise conflict()
                response = TurnResponse.model_validate(previous["response"])
            else:
                self.events.ready()
                outcome = handler(request, context.model_copy(update={"session_id": session_id}))
                response = TurnResponse.model_validate(outcome.model_dump(mode="json"))
                if request.mode == "fixed" and response.llm_call_count != 0:
                    raise conflict(ErrorCode.ILLEGAL_STATE)
                created_at = datetime.now(UTC)
                tx.execute(
                    "INSERT INTO turns "
                    "(namespace,request_id,turn_id,session_id,user_id,"
                    "request_hash,response,created_at,intent_diagnostic) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        context.namespace,
                        request.request_id,
                        response.turn_id,
                        session_id,
                        context.user_id,
                        digest,
                        Jsonb(response.model_dump(mode="json")),
                        created_at,
                        Jsonb(outcome.diagnostic) if hasattr(outcome, "diagnostic") else None,
                    ),
                )
                self._event(
                    tx,
                    row,
                    context,
                    "CONVERSATION_TURN",
                    {
                        "turn_id": response.turn_id,
                        "mode": request.mode,
                        "outcome": response.outcome,
                        "duration_ms": response.timings_ms.total,
                        "llm_call_count": response.llm_call_count,
                        "extractor_source": response.extractor_source,
                    },
                    created_at,
                )
            self._save(tx, scope, digest, response)
            return response
