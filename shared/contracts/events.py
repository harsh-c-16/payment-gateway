"""Version-one event snapshots. Producer owners review these before G0 freeze."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from shared.contracts.common import Identifier, Money, Sku, UTCTime, UUIDText

Positive = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
SchemaVersion = Annotated[int, Field(strict=True, ge=1, le=1)]
Count = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
Duration = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Namespace = Annotated[
    str, Field(pattern=r"^(dev|(?:bench|replay)-[a-z0-9-]{1,54})$", max_length=62)
]
IsolatedNamespace = Annotated[str, Field(pattern=r"^(?:bench|replay)-[a-z0-9-]{1,54}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Service = Literal["conversation", "catalog", "orders", "inventory", "payments", "benchmark"]
DiagnosticService = Literal[
    "conversation", "catalog", "orders", "inventory", "payments", "benchmark", "analytics"
]
FacetValue = Annotated[str, Field(min_length=1, max_length=256)]
RETRIEVAL_MODES = frozenset(
    ("filter_only", "lexical", "vector_exact", "hybrid_exact", "hybrid_ann")
)


class ReasonCode(StrEnum):
    INVALID_UTF8 = "INVALID_UTF8"
    INVALID_JSON = "INVALID_JSON"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    SCHEMA_ID_MISMATCH = "SCHEMA_ID_MISMATCH"
    KEY_MISMATCH = "KEY_MISMATCH"
    UNKNOWN_DICTIONARY_VALUE = "UNKNOWN_DICTIONARY_VALUE"
    EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"
    AGGREGATE_VERSION_CONFLICT = "AGGREGATE_VERSION_CONFLICT"
    UNKNOWN_SKU = "UNKNOWN_SKU"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"


class EventModel(BaseModel):
    # Preserve the immutable wire object separately; readers tolerate optional additions.
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class IntentSnapshot(EventModel):
    """Embedded event snapshot of common §4; not Harsh's API ShoppingIntent DTO."""

    query_text: Annotated[str, Field(max_length=2000)]
    category: FacetValue | None
    size: FacetValue | None
    colour: FacetValue | None
    material: FacetValue | None
    max_price_minor: Money | None
    occasion: FacetValue | None
    currency: Literal["INR"]
    brand: FacetValue | None = None
    category_path_prefix: list[FacetValue] | None = None


class ConversationTurn(EventModel):
    turn_id: UUIDText
    mode: Literal["fixed", "assist"]
    outcome: Literal["success", "clarification", "dependency_error"]
    duration_ms: Duration
    llm_call_count: Annotated[int, Field(strict=True, ge=0, le=1)]
    extractor_source: Literal["rules", "llm", "clarification"]

    @model_validator(mode="after")
    def fixed_has_no_model_call(self):
        if self.mode == "fixed" and self.llm_call_count != 0:
            raise ValueError("fixed mode must make zero generative calls")
        return self


class IntentExtracted(EventModel):
    turn_id: UUIDText
    intent: IntentSnapshot
    extractor_version: Identifier
    outcome: Literal["valid"]


class IntentRejected(EventModel):
    turn_id: UUIDText
    reason_code: Identifier
    extractor_version: Identifier
    restricted_content_reference: Identifier


class ToolCalled(EventModel):
    turn_id: UUIDText
    tool_call_id: UUIDText
    tool_name: Identifier
    outcome: Identifier
    duration_ms: Duration


class AddToCart(EventModel):
    cart_id: UUIDText
    cart_version: Positive
    sku: Sku
    quantity_after: Annotated[int, Field(strict=True, ge=0, le=10)]


class CheckoutStarted(EventModel):
    cart_id: UUIDText
    quote_id: UUIDText
    order_id: UUIDText
    confirmation_id: UUIDText


class SearchRequested(EventModel):
    search_id: UUIDText
    intent: IntentSnapshot
    mode: Identifier

    @model_validator(mode="after")
    def supported_mode(self):
        if self.mode not in RETRIEVAL_MODES:
            raise ValueError("unsupported retrieval mode")
        return self


class ProductRetrieved(EventModel):
    search_id: UUIDText
    skus: Annotated[list[Sku], Field(max_length=20)]
    returned_count: Annotated[int, Field(strict=True, ge=0, le=20)]
    mode: Identifier
    duration_ms: Duration

    @model_validator(mode="after")
    def coherent_count(self):
        if self.mode not in RETRIEVAL_MODES:
            raise ValueError("unsupported retrieval mode")
        if self.returned_count != len(self.skus) or len(set(self.skus)) != len(self.skus):
            raise ValueError("returned count and unique SKU list must agree")
        return self


class ProductCompared(EventModel):
    comparison_id: UUIDText
    skus: Annotated[list[Sku], Field(min_length=1, max_length=20)]
    field_names: Annotated[list[Identifier], Field(min_length=1)]


class PriceUpdated(EventModel):
    sku: Sku
    price_minor: Annotated[int, Field(strict=True, ge=1, le=1_000_000_000)]
    currency: Literal["INR"]
    catalog_version: Positive


class OrderEvent(EventModel):
    order_id: UUIDText
    order_status: Literal["PENDING", "CONFIRMED", "CANCELLED"]
    total_amount_minor: Money
    currency: Literal["INR"]
    created_at: UTCTime
    user_id: Identifier
    session_id: UUIDText
    quote_id: UUIDText
    failure_code: Identifier | None


class OrderConfirmed(OrderEvent):
    reservation_id: UUIDText
    payment_id: UUIDText


class InventoryEvent(EventModel):
    sku: Sku
    on_hand: Count
    reserved: Count
    available: Count
    stock_version: Positive
    changed_at: UTCTime
    order_id: UUIDText | None
    reservation_id: UUIDText | None
    reason_code: Identifier | None

    @model_validator(mode="after")
    def absolute_stock(self):
        if self.reserved > self.on_hand or self.available != self.on_hand - self.reserved:
            raise ValueError("available must equal on_hand minus reserved")
        return self


class InventoryRejected(InventoryEvent):
    order_id: UUIDText
    reason_code: Identifier
    reservation_request_id: UUIDText


class PaymentEvent(EventModel):
    payment_id: UUIDText
    order_id: UUIDText
    attempt_number: Positive
    status: Literal["PENDING", "SUCCESS", "FAILED", "CANCELLED", "REVERSED"]
    amount_minor: Money
    currency: Literal["INR"]
    attempt_created_at: UTCTime
    failure_code: Identifier | None
    debit_id: UUIDText | None
    reversal_id: UUIDText | None


# event_type -> (domain, producer, aggregate type, Kafka key field, payload model)
EVENTS = {
    **{
        name: ("conversation-events", "conversation", "session", "session_id", model)
        for name, model in {
            "CONVERSATION_TURN": ConversationTurn,
            "INTENT_EXTRACTED": IntentExtracted,
            "INTENT_REJECTED": IntentRejected,
            "TOOL_CALLED": ToolCalled,
            "ADD_TO_CART": AddToCart,
            "CHECKOUT_STARTED": CheckoutStarted,
        }.items()
    },
    **{
        name: ("retrieval-events", "catalog", "search", "session_id", model)
        for name, model in {
            "SEARCH_REQUESTED": SearchRequested,
            "PRODUCT_RETRIEVED": ProductRetrieved,
            "PRODUCT_COMPARED": ProductCompared,
        }.items()
    },
    "PRICE_UPDATED": ("retrieval-events", "catalog", "sku", "sku", PriceUpdated),
    **{
        name: ("order-events", "orders", "order", "order_id", model)
        for name, model in {
            "ORDER_CREATED": OrderEvent,
            "ORDER_CONFIRMED": OrderConfirmed,
            "ORDER_CANCELLED": OrderEvent,
        }.items()
    },
    **{
        name: ("inventory-events", "inventory", "sku", "sku", model)
        for name, model in {
            "STOCK_UPDATED": InventoryEvent,
            "INVENTORY_RESERVED": InventoryEvent,
            "INVENTORY_RELEASED": InventoryEvent,
            "INVENTORY_EXPIRED": InventoryEvent,
            "INVENTORY_COMMITTED": InventoryEvent,
            "INVENTORY_REJECTED": InventoryRejected,
        }.items()
    },
    **{
        f"PAYMENT_{status}": (
            "payment-events",
            "payments",
            "payment_attempt",
            "order_id",
            PaymentEvent,
        )
        for status in ("PENDING", "SUCCESS", "FAILED", "CANCELLED", "REVERSED")
    },
}


class EventMetadata(EventModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    dataset_revision: Identifier | None = None
    synthetic: Annotated[bool, Field(strict=True)] | None = None
    scenario_source: Literal["simulation", "benchmark"] | None = None
    original_event_id: UUIDText | None = None


class EventEnvelope(EventModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    event_id: UUIDText
    event_type: str
    schema_version: SchemaVersion
    event_time: UTCTime
    produced_at: UTCTime
    namespace: Namespace
    run_id: Identifier
    source_service: Service
    correlation_id: UUIDText
    session_id: UUIDText | None
    user_id: Identifier | None
    aggregate_type: Literal["session", "search", "order", "sku", "payment_attempt"]
    aggregate_id: Identifier
    aggregate_version: Positive
    payload: dict[str, JsonValue]
    metadata: EventMetadata

    @model_validator(mode="after")
    def semantics(self):
        if type(self.schema_version) is not int:
            raise ValueError("schema_version must be an integer")
        if self.event_type not in EVENTS:
            raise ValueError("unsupported event type")
        domain, producer, aggregate, key, model = EVENTS[self.event_type]
        payload = model.model_validate(self.payload)
        if self.aggregate_type != aggregate:
            raise ValueError("wrong aggregate type")
        if self.source_service == "benchmark":
            if not self.namespace.startswith("bench-") or not self.metadata.synthetic:
                raise ValueError("benchmark producer requires an isolated synthetic benchmark")
            if self.metadata.scenario_source != "benchmark":
                raise ValueError("benchmark provenance is required")
        elif self.source_service != producer:
            raise ValueError("event producer does not own this event type")
        if domain == "conversation-events" or (
            domain == "retrieval-events" and key == "session_id"
        ):
            if self.session_id is None or self.user_id is None:
                raise ValueError("session events require session and user identity")
        expected_id = (
            self.session_id
            if aggregate == "session"
            else self.payload.get(
                {"sku": "sku", "order": "order_id", "payment_attempt": "payment_id"}.get(
                    aggregate,
                    "search_id" if self.event_type != "PRODUCT_COMPARED" else "comparison_id",
                )
            )
        )
        if self.aggregate_id != expected_id:
            raise ValueError("aggregate ID does not match payload identity")
        if isinstance(payload, InventoryEvent) and self.aggregate_version != payload.stock_version:
            raise ValueError("aggregate version must equal stock version")
        if isinstance(payload, PriceUpdated) and self.aggregate_version != payload.catalog_version:
            raise ValueError("aggregate version must equal catalogue version")
        if domain in ("retrieval-events", "order-events", "inventory-events", "payment-events") or (
            self.event_type in ("ADD_TO_CART", "CHECKOUT_STARTED")
        ):
            if self.metadata.dataset_revision is None:
                raise ValueError("catalogue-linked facts require dataset_revision")
        if domain in ("order-events", "inventory-events", "payment-events"):
            if not self.metadata.synthetic or self.metadata.scenario_source not in (
                "simulation",
                "benchmark",
            ):
                raise ValueError("simulated transactions require explicit provenance")
        if isinstance(payload, PaymentEvent) and self.event_type != f"PAYMENT_{payload.status}":
            raise ValueError("payment event type and status disagree")
        if isinstance(payload, OrderEvent):
            status = {
                "ORDER_CREATED": "PENDING",
                "ORDER_CONFIRMED": "CONFIRMED",
                "ORDER_CANCELLED": "CANCELLED",
            }[self.event_type]
            if payload.order_status != status:
                raise ValueError("order event type and status disagree")
        return self

    def kafka_key(self) -> str:
        field = EVENTS[self.event_type][3]
        return self.session_id if field == "session_id" else self.payload[field]

    def topic(self) -> str:
        return f"{self.namespace}.{EVENTS[self.event_type][0]}.v1"


class SourceLocator(EventModel):
    topic: str
    partition: Count
    offset: Count
    raw_locator: Identifier


class LocalDiagnostic(EventModel):
    diagnostic_id: UUIDText
    namespace: Namespace
    run_id: Identifier
    source_service: DiagnosticService
    reason_code: ReasonCode
    correlation_id: UUIDText
    created_at: UTCTime
    content_hash: Sha256
    restricted_content_reference: Identifier
    source_coordinates: SourceLocator | None


class DlqNotice(EventModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    event_id: UUIDText
    diagnostic_id: UUIDText
    namespace: Namespace
    run_id: Identifier
    schema_version: SchemaVersion
    produced_at: UTCTime
    source_service: DiagnosticService
    origin_kind: Literal["kafka_record", "service_diagnostic"]
    source_locator: SourceLocator | Identifier
    reason_code: ReasonCode
    created_at: UTCTime

    @model_validator(mode="after")
    def identity(self):
        if type(self.schema_version) is not int or self.event_id != self.diagnostic_id:
            raise ValueError("DLQ event_id must equal diagnostic_id; version must be integer one")
        if self.origin_kind == "kafka_record" and not isinstance(
            self.source_locator, SourceLocator
        ):
            raise ValueError("Kafka diagnostics require source coordinates")
        return self

    def kafka_key(self) -> str:
        return self.diagnostic_id

    def topic(self) -> str:
        return f"{self.namespace}.dead-letter.v1"


RegisteredRecord = EventEnvelope | DlqNotice


class ValidationFailure(EventModel):
    reason_code: ReasonCode
    field_path: str | None
    diagnostic_message: str
    original_content_hash: Sha256


class PublishAck(EventModel):
    event_id: UUIDText
    topic: str
    partition: Count
    offset: Count
    broker_acked_at: UTCTime


@dataclass(frozen=True)
class SourceRecord:
    source_namespace: str
    topic: str
    partition: int
    offset: int
    key_bytes: bytes | None
    value_bytes: bytes | None
    headers: tuple[tuple[str, bytes | None], ...]
    broker_timestamp: datetime | None
    ingested_at: datetime
    raw_sha256: str
    assignment_epoch: str = ""


@dataclass(frozen=True)
class ValidEvent:
    envelope: RegisteredRecord
    schema_id: int
    canonical_content_hash: str
    source_record: SourceRecord | None
    document: dict[str, JsonValue]


@dataclass(frozen=True)
class CommittedOffset:
    topic: str
    partition: int
    offset: int


@dataclass(frozen=True)
class CommitResult:
    group_id: str
    committed_next_offsets: tuple[CommittedOffset, ...]
    succeeded: bool
    error: str | None
