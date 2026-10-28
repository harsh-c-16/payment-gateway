"""Save P2 wire pairs and negative evidence using explicit test-only doubles."""

import argparse
import asyncio
import copy
import json
import socket
from pathlib import Path

import httpx

from services.conversation.clients import (
    CatalogClient,
    DependencyUnavailable,
    ProviderHTTP,
    TransportConfig,
)
from services.conversation.provider_contracts import ENDPOINTS, ContractViolation, OpenAPIContracts
from shared.contracts.common import RequestContext

from .doubles import Chunks, ScriptedProvider, sse
from .provisional import ROOT, ProvisionalContracts, uid
from .test_clients import http_for, invoke


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def probe(out):
    pairs = json.loads((ROOT / "contracts/fixtures/p2/pairs.json").read_text(encoding="utf-8"))[
        "pairs"
    ]
    context = RequestContext(
        namespace="bench-p2",
        run_id=uid(10),
        user_id="p2-user",
        correlation_id=uid(11),
        request_id=uid(1),
        session_id=uid(2),
    )
    journal = []
    for pair in pairs:
        if ENDPOINTS[pair["endpoint"]].stream:

            async def provider(request, pair=pair):
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=Chunks([sse(pair["response"])]),
                )

            double = ScriptedProvider(provider)
            async with http_for(double) as http:
                observed = [value async for value in http.events(uid(6), context)][0]
        else:
            double = ScriptedProvider((ENDPOINTS[pair["endpoint"]].status, pair["response"]))
            async with http_for(double) as http:
                observed = await invoke(http, pair, context)
        request = double.requests[0]
        assert observed == pair["response"]
        journal.append(
            {
                "test_mode": "stub",
                "provisional": True,
                "case": pair["name"],
                "endpoint": pair["endpoint"],
                "method": request.method,
                "url": str(request.url),
                "headers": {
                    key: value
                    for key, value in request.headers.items()
                    if key.lower() != "authorization"
                },
                "request": pair["request"],
                "response": observed,
            }
        )
    (out / "request-response.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in journal), encoding="utf-8"
    )
    negative = []
    search = copy.deepcopy(next(pair for pair in pairs if pair["name"] == "five-hits")["response"])
    search["returned_cout"] = search.pop("returned_count")
    quote = copy.deepcopy(next(pair for pair in pairs if pair["endpoint"] == "quote")["response"])
    quote["total_amount_minor"] = "39900"
    for name, endpoint, payload in [
        ("misspelled-required-field", "search", search),
        ("money-is-string", "quote", quote),
    ]:
        try:
            ProvisionalContracts().validate(ENDPOINTS[endpoint], "response", payload)
        except ContractViolation as error:
            negative.append(
                {
                    "test_mode": "stub",
                    "case": name,
                    "rejected": True,
                    "error": str(error),
                    "corrupt_payload": payload,
                }
            )
        else:
            raise AssertionError("negative contract corruption was not rejected")
    save(out / "negative-checks.json", negative)
    with socket.socket() as stopped:
        stopped.bind(("127.0.0.1", 0))
        config = TransportConfig(
            f"http://127.0.0.1:{stopped.getsockname()[1]}", timeout_seconds=0.1, get_retries=0
        )
        try:
            async with ProviderHTTP(config, OpenAPIContracts(ROOT / "contracts/http")) as http:
                await CatalogClient(http).product("FK-P2-SYNTHETIC-001", context)
        except DependencyUnavailable as error:
            save(
                out / "real-stopped-provider.json",
                {
                    "transport_mode": "real",
                    "real_integration_passed": False,
                    "provider_stopped": True,
                    "expected_dependency_failure_observed": True,
                    "fixture_fallback": False,
                    "error": str(error),
                },
            )
        else:
            raise AssertionError("real stopped provider unexpectedly succeeded")
    print(
        json.dumps(
            {
                "stub_wire_pairs": len(journal),
                "negative_corruptions_rejected": len(negative),
                "real_stopped_provider": "dependency failure observed; no fallback",
                "real_integration": "NOT_RUN",
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    asyncio.run(probe(args.out))


if __name__ == "__main__":
    main()
