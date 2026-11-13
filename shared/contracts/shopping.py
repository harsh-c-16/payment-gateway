"""Browser shopping extensions; the frozen fixed-workflow request stays unchanged."""

from typing import Annotated, Literal

from pydantic import Field

from shared.contracts.common import Identifier, Sku, UUIDText, WireModel
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
