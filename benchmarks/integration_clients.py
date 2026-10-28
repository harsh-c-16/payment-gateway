"""Real M1 HTTP consumer for IntegratedDriver, with explicit contract-test transport."""

from urllib.parse import quote

import httpx

from services.conversation.clients import DependencyUnavailable, RemoteError, strict_json
from services.conversation.provider_contracts import ContractViolation, Endpoint
from shared.contracts.common import ErrorResponse


class ConversationHTTP:
    """No hidden retries: recovery trials must explicitly retry the original key."""

    def __init__(self, config, contracts, *, transport=None):
        if config.mode == "real":
            if transport is not None or contracts.mode != "real":
                raise ValueError("real M1 adapter requires real HTTP and owner contracts")
            transport = httpx.AsyncHTTPTransport(retries=0)
        elif config.mode != "stub" or transport is None or contracts.mode != "stub":
            raise ValueError("contract tests require explicit stub transport/contracts")
        self.config, self.contracts = config, contracts
        self.http = httpx.AsyncClient(
            base_url=config.base_url,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=config.timeout_seconds,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http.aclose()

    async def call(self, context, method, template, status, body, key, **identifiers):
        endpoint = Endpoint("conversation", method, template, status)
        path = template
        for name, value in identifiers.items():
            if not isinstance(value, str) or not value or value in {".", ".."}:
                raise ValueError("invalid resource identifier")
            path = path.replace("{" + name + "}", quote(value, safe=""))
        if "{" in path or not key:
            raise ValueError("complete identifiers and stable idempotency key required")
        if identifiers.get("session_id", context.session_id) != context.session_id:
            raise ValueError("session/context identity mismatch")
        self.contracts.validate(endpoint, "request", body)
        try:
            response = await self.http.request(
                method, path, json=body, headers=context.headers(key)
            )
        except httpx.TransportError as exc:
            raise DependencyUnavailable(outcome_unknown=True) from exc
        value = strict_json(response.content)
        if response.status_code != status:
            if response.status_code < 400:
                raise ContractViolation("unexpected M1 success/redirect status")
            try:
                error = ErrorResponse.model_validate(value)
            except ValueError as exc:
                raise ContractViolation("invalid M1 error contract") from exc
            raise RemoteError(response.status_code, error)
        self.contracts.validate(endpoint, "response", value)
        return value

    async def create_session(self, context, *, key):
        return await self.call(context, "POST", "/v1/sessions", 201, {}, key)

    async def turn(self, context, *, text, mode, key):
        return await self.call(
            context,
            "POST",
            "/v1/sessions/{session_id}/turns",
            200,
            {"request_id": context.request_id, "text": text, "mode": mode},
            key,
            session_id=context.session_id,
        )

    async def update(self, context, cart_id, sku, *, quantity, expected_cart_version, key):
        return await self.call(
            context,
            "PUT",
            "/v1/carts/{cart_id}/items/{sku}",
            200,
            {"quantity": quantity, "expected_cart_version": expected_cart_version},
            key,
            cart_id=cart_id,
            sku=sku,
        )

    async def quote(self, context, cart_id, *, expected_cart_version, key):
        return await self.call(
            context,
            "POST",
            "/v1/carts/{cart_id}/quote",
            201,
            {"expected_cart_version": expected_cart_version},
            key,
            cart_id=cart_id,
        )

    async def checkout(
        self, context, cart_id, *, quote_id, expected_cart_version, confirmed, confirmation_id, key
    ):
        return await self.call(
            context,
            "POST",
            "/v1/carts/{cart_id}/checkout",
            202,
            {
                "quote_id": quote_id,
                "expected_cart_version": expected_cart_version,
                "confirmed": confirmed,
                "confirmation_id": confirmation_id,
            },
            key,
            cart_id=cart_id,
        )
