"""Short-lived HTTP transports avoid sharing async pools between worker loops."""

from pathlib import Path

from .clients import ProviderHTTP, TransportConfig
from .provider_contracts import ENDPOINTS, OpenAPIContracts


class Gateway:
    def __init__(
        self,
        catalog_url,
        orders_url,
        *,
        contracts=None,
        transport=None,
        mode="real",
        purpose="integration",
    ):
        self.mode = mode
        self.purpose = purpose
        self.contracts = contracts or OpenAPIContracts(
            Path(__file__).resolve().parents[2] / "contracts/http"
        )
        if mode == "real" and (self.contracts.mode != "real" or transport is not None):
            raise ValueError("real gateway requires owner contracts and real HTTP")
        if mode == "stub" and (
            purpose != "contract_test" or transport is None or self.contracts.mode != "stub"
        ):
            raise ValueError("gateway doubles require explicit stub/contract_test mode")
        self.transport = transport
        self.configs = {
            "catalog": TransportConfig(catalog_url, mode=mode, purpose=purpose),
            "transactions": TransportConfig(orders_url, mode=mode, purpose=purpose),
        }

    def ready(self):
        for name in ("facets", "search", "quote", "order_create", "order_status"):
            if self.mode == "real":
                self.contracts.operation(ENDPOINTS[name])

    async def call(self, name, context, **kwargs):
        async with ProviderHTTP(
            self.configs[ENDPOINTS[name].provider], self.contracts, transport=self.transport
        ) as http:
            return await http.request(name, context, **kwargs)
