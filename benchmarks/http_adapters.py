"""Real public HTTP bindings; short-lived clients preserve the no-reuse baseline."""

import os

from benchmarks.integration_clients import ConversationHTTP
from projectctl.config import repo_path
from services.conversation.clients import CatalogClient, OrdersClient, ProviderHTTP, TransportConfig
from services.conversation.provider_contracts import OpenAPIContracts


class CatalogRequests:
    async def _call(self, name, *args, **kwargs):
        config = TransportConfig(
            os.environ.get("CATALOG_BASE_URL", "http://localhost:8002"), purpose="benchmark"
        )
        async with ProviderHTTP(config, OpenAPIContracts(repo_path("contracts/http"))) as http:
            return await getattr(CatalogClient(http), name)(*args, **kwargs)

    async def search(self, *args, **kwargs):
        return await self._call("search", *args, **kwargs)

    async def quote(self, *args, **kwargs):
        return await self._call("quote", *args, **kwargs)


class OrdersRequests:
    async def create(self, *args, **kwargs):
        config = TransportConfig(
            os.environ.get("ORDERS_BASE_URL", "http://localhost:8003"), purpose="benchmark"
        )
        async with ProviderHTTP(config, OpenAPIContracts(repo_path("contracts/http"))) as http:
            return await OrdersClient(http).create(*args, **kwargs)


class ConversationRequests:
    async def _call(self, name, *args, **kwargs):
        config = TransportConfig(
            os.environ.get("CONVERSATION_BASE_URL", "http://localhost:8001"), purpose="benchmark"
        )
        async with ConversationHTTP(config, OpenAPIContracts(repo_path("contracts/http"))) as http:
            return await getattr(http, name)(*args, **kwargs)

    async def create_session(self, *args, **kwargs):
        return await self._call("create_session", *args, **kwargs)

    async def turn(self, *args, **kwargs):
        return await self._call("turn", *args, **kwargs)

    async def update(self, *args, **kwargs):
        return await self._call("update", *args, **kwargs)

    async def quote(self, *args, **kwargs):
        return await self._call("quote", *args, **kwargs)

    async def checkout(self, *args, **kwargs):
        return await self._call("checkout", *args, **kwargs)
