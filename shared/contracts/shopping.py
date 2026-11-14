"""Browser shopping extensions; the frozen fixed-workflow request stays unchanged."""

from typing import Annotated, Literal

from pydantic import Field

from shared.contracts.common import Identifier, Sku, UTCTime, UUIDText, WireModel
from shared.contracts.conversation import ProviderObject, TurnRequest

ShoppingSearchMode = Literal["lexical", "hybrid_exact"]


class ShoppingTurnRequest(TurnRequest):
    selected_sku: Sku | None = None
    retrieval_mode: ShoppingSearchMode | None = None


class ShoppingMemory(WireModel):
    intent: ProviderObject | None = None
    pending: list[str] = Field(default_factory=list)
    products: Annotated[list[ProviderObject], Field(max_length=20)] = Field(default_factory=list)
    seen_skus: Annotated[list[Sku], Field(max_length=200)] = Field(default_factory=list)
    selected_sku: Sku | None = None
    retrieval_mode: ShoppingSearchMode = "lexical"
    messages: Annotated[list[ProviderObject], Field(max_length=40)] = Field(default_factory=list)


class ShoppingSession(WireModel):
    session_id: UUIDText
    cart_id: UUIDText
    conversation: ShoppingMemory


class ShoppingBootstrap(WireModel):
    namespace: Identifier
    simulation: Literal[True] = True
    conversation_available: bool = False
    conversation_model: str | None = None


class OrderPipelineStatus(WireModel):
    order_id: UUIDText
    order_version: Annotated[int, Field(ge=1)]
    status: Literal["pending", "visible", "unavailable"]
    generation: Annotated[int, Field(ge=1)] | None = None
    checked_at: UTCTime


class ShoppingMetrics(WireModel):
    session_id: UUIDText
    sampled_turns: Annotated[int, Field(ge=0, le=500)]
    sample_limit: Literal[500] = 500
    searches: Annotated[int, Field(ge=0)]
    model_attempts: Annotated[int, Field(ge=0)]
    query_embeddings: Annotated[int, Field(ge=0)]
    dependency_errors: Annotated[int, Field(ge=0)]
    turn_p50_ms: float | None
    turn_p95_ms: float | None
    model_mean_ms: float | None
    session_outbox_pending: Annotated[int, Field(ge=0)]
    pipeline_status: Literal["available", "unavailable"]
    pipeline_events_today: Annotated[int, Field(ge=0)] | None
    pipeline_events_by_type: dict[str, int] | None
    gold_generation: Annotated[int, Field(ge=1)] | None
    pipeline_date_utc: str
    checked_at: UTCTime


class DashboardSnapshot(WireModel):
    namespace: Identifier
    checked_at: UTCTime
    pipeline_date_utc: str
    session: ShoppingMetrics
    activity: ProviderObject
    pipeline: ProviderObject | None
    datasets: list[ProviderObject]
    catalogue: ProviderObject | None
    services: list[ProviderObject]
    receipt_sample: ProviderObject | None
    orders: ProviderObject | None
    unavailable: list[str]
