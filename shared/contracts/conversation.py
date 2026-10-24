"""M1 contracts only. Provider-owned nested JSON is validated by its OpenAPI schema.

No catalogue, quote, transaction, or event DTO is defined here. Their OpenAPI
references remain external; missing provider contracts block the full gate.
"""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from shared.contracts.common import Identifier, Money, Sku, UTCTime, UUIDText, Version, WireModel

Quantity = Annotated[int, Field(strict=True, ge=1, le=10)]
Duration = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
ProviderObject = dict[str, JsonValue]


class SessionCreated(WireModel):
    session_id: UUIDText
    cart_id: UUIDText
    cart_version: Annotated[int, Field(strict=True, ge=0, le=0)]


class TurnRequest(WireModel):
    request_id: UUIDText
    text: Annotated[str, Field(max_length=2000)]
    mode: Literal["fixed", "assist"] = "fixed"


class TurnTimings(WireModel):
    parse: Duration
    llm: Duration | None
    search: Duration
    compose: Duration
    total: Duration


class TurnResponse(WireModel):
    turn_id: UUIDText
    response_text: str
    intent: ProviderObject | None
    search_id: UUIDText | None
    products: Annotated[list[ProviderObject], Field(max_length=20)]
    proposed_action: ProviderObject | None
    outcome: Literal["success", "clarification", "dependency_error"]
    extractor_source: Literal["rules", "llm", "clarification"]
    llm_call_count: Annotated[int, Field(strict=True, ge=0, le=1)]
    timings_ms: TurnTimings

    @model_validator(mode="after")
    def model_timing(self):
        if self.llm_call_count == 0 and self.timings_ms.llm is not None:
            raise ValueError("an unexecuted model has no latency sample")
        return self


class CartLine(WireModel):
    sku: Sku
    quantity: Quantity
    display_price_minor: Money | None


class CartSnapshot(WireModel):
    cart_id: UUIDText
    session_id: UUIDText
    user_id: Identifier
    version: Version
    lines: Annotated[list[CartLine], Field(max_length=20)]
    updated_at: UTCTime

    @model_validator(mode="after")
    def unique_skus(self):
        if len({line.sku for line in self.lines}) != len(self.lines):
            raise ValueError("cart SKU lines must be unique")
        return self


class CartUpdateRequest(WireModel):
    quantity: Annotated[int, Field(strict=True, ge=0, le=10)]
    expected_cart_version: Version


class CartQuoteRequest(WireModel):
    expected_cart_version: Version


class CheckoutRequest(WireModel):
    quote_id: UUIDText
    expected_cart_version: Version
    confirmed: Annotated[bool, Field(strict=True)]
    confirmation_id: UUIDText

    @model_validator(mode="after")
    def explicit_confirmation(self):
        if self.confirmed is not True:
            raise ValueError("explicit confirmation is required")
        return self
