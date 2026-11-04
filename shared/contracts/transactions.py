"""Transaction DTOs for Orders, Inventory and Payments. Owner: Aditya."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from shared.contracts.common import (
    Identifier,
    Money,
    Sku,
    UTCTime,
    UUIDText,
    Version,
    WireModel,
)


Quantity = Annotated[int, Field(strict=True, ge=1, le=10)]
Positive = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
AttemptNumber = Annotated[int, Field(strict=True, ge=1, le=2)]


# ── Quote line (copied from catalogue at order creation) ──


class QuoteLine(WireModel):
    sku: Sku
    quantity: Quantity
    unit_price_minor: Positive
    line_total_minor: Positive
    catalog_version: Positive

    @model_validator(mode="after")
    def line_total_check(self):
        if self.line_total_minor != self.unit_price_minor * self.quantity:
            raise ValueError("line_total must equal unit_price * quantity")
        return self


# ── Orders ──


OrderStatus = Literal[
    "PENDING", "RESERVING", "PAYMENT_PENDING", "COMMITTING_STOCK",
    "CONFIRMED", "COMPENSATING", "CANCELLED", "MANUAL_REVIEW",
]


class CreateOrderRequest(WireModel):
    quote_id: UUIDText
    session_id: UUIDText
    confirmation_id: UUIDText


class OrderAccepted(WireModel):
    order_id: UUIDText
    status: str
    status_url: str


class OrderSnapshot(WireModel):
    order_id: UUIDText
    quote_id: UUIDText
    user_id: Identifier
    session_id: UUIDText
    status: OrderStatus
    order_version: Positive
    lines: Annotated[list[QuoteLine], Field(min_length=1, max_length=20)]
    total_amount_minor: Money
    currency: Literal["INR"]
    reservation_id: UUIDText | None = None
    payment_id: UUIDText | None = None
    failure_code: str | None = None
    created_at: UTCTime
    updated_at: UTCTime


# ── Inventory ──


ReservationState = Literal["ACTIVE", "COMMITTED", "RELEASED", "EXPIRED"]


class ReserveItem(WireModel):
    sku: Sku
    quantity: Quantity


class ReserveRequest(WireModel):
    order_id: UUIDText
    items: Annotated[list[ReserveItem], Field(min_length=1, max_length=20)]
    ttl_seconds: Annotated[int, Field(strict=True, ge=1)] = 30


class InventoryReceipt(WireModel):
    sku: Sku
    stock_version: Positive


class ReservationSnapshot(WireModel):
    reservation_id: UUIDText
    order_id: UUIDText
    state: ReservationState
    items: list[ReserveItem]
    expires_at: UTCTime
    inventory_receipts: list[InventoryReceipt] = []
    updated_at: UTCTime


class StockSnapshot(WireModel):
    sku: Sku
    on_hand: Annotated[int, Field(strict=True, ge=0)]
    reserved: Annotated[int, Field(strict=True, ge=0)]
    available: Annotated[int, Field(strict=True, ge=0)]
    stock_version: Positive
    changed_at: UTCTime

    @model_validator(mode="after")
    def invariant(self):
        if self.reserved > self.on_hand or self.available != self.on_hand - self.reserved:
            raise ValueError("available must equal on_hand minus reserved")
        return self


# ── Payments ──


PaymentStatus = Literal["PENDING", "SUCCESS", "FAILED", "CANCELLED", "REVERSED"]


class AuthorizePaymentRequest(WireModel):
    order_id: UUIDText
    attempt_number: AttemptNumber
    amount_minor: Money
    currency: Literal["INR"]


class PaymentSnapshot(WireModel):
    payment_id: UUIDText
    order_id: UUIDText
    attempt_number: AttemptNumber
    status: PaymentStatus
    amount_minor: Money
    currency: Literal["INR"]
    failure_code: str | None = None
    debit_id: UUIDText | None = None
    reversal_id: UUIDText | None = None
    created_at: UTCTime
    updated_at: UTCTime


class PaymentOrderSnapshot(WireModel):
    attempts: list[PaymentSnapshot]
    quiesced: Annotated[bool, Field(strict=True)]
    net_debit_minor: Money
