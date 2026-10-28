"""Offline compatibility inventory. A partial consumer pass cannot complete G0."""

import json
from pathlib import Path

import yaml

from projectctl.conversation_contract import document
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult
from services.conversation.provider_contracts import (
    ENDPOINTS,
    ContractUnavailable,
    ContractViolation,
    OpenAPIContracts,
)

OWNERS = {"catalog": "Harsh", "transactions": "Aditya", "analytics": "Vichitr"}

# Full §5 participant surface, even where P2 clients do not issue these commands.
PARTICIPANTS = [
    ("POST", "/internal/v1/reservations"),
    ("GET", "/internal/v1/reservations/by-order/{order_id}"),
    ("POST", "/internal/v1/reservations/by-order/{order_id}/commit"),
    ("POST", "/internal/v1/reservations/by-order/{order_id}/release"),
    ("GET", "/internal/v1/inventory/{sku}"),
    ("POST", "/internal/v1/payments/authorize"),
    ("GET", "/internal/v1/payments/by-order/{order_id}"),
    ("POST", "/internal/v1/payments/by-order/{order_id}/reverse"),
]


def inspect_contracts(root: Path):
    checks = []

    def add(name, owner, status, detail):
        checks.append({"name": name, "owner": owner, "status": status, "detail": detail})

    conversation = root / "contracts/http/conversation.yaml"
    try:
        actual = yaml.safe_load(conversation.read_text(encoding="utf-8"))
        if actual != document():
            raise ValueError("owned OpenAPI differs from DTOs/generator")
        add(
            "contracts/http/conversation.yaml",
            "Jaineel",
            "PASS",
            "local owned schema current; external refs pending",
        )
    except (OSError, ValueError, yaml.YAMLError):
        add(
            "contracts/http/conversation.yaml",
            "Jaineel",
            "FAIL",
            "owned OpenAPI missing, malformed or stale",
        )
    contracts = OpenAPIContracts(root / "contracts/http")
    documents = {}
    for provider, owner in OWNERS.items():
        path = root / "contracts/http" / (provider + ".yaml")
        try:
            documents[provider] = contracts._document(path)
            add(
                path.relative_to(root).as_posix(),
                owner,
                "PASS",
                "OpenAPI 3.1 present; checking consumed examples",
            )
        except ContractUnavailable:
            add(
                path.relative_to(root).as_posix(),
                owner,
                "MISSING",
                "owner OpenAPI absent or unsupported; no replacement DTO supplied",
            )
    for name, endpoint in ENDPOINTS.items():
        if endpoint.provider not in documents:
            add(
                name,
                OWNERS[endpoint.provider],
                "MISSING",
                f"{endpoint.method} {endpoint.path}; canonical request/response schema pending",
            )
            continue
        try:
            operation = contracts.operation(endpoint)
            response = operation["responses"][str(endpoint.status)]
            media = "text/event-stream" if endpoint.stream else "application/json"
            if media not in response["content"]:
                raise KeyError
            add(
                name,
                OWNERS[endpoint.provider],
                "PASS",
                f"{endpoint.method} {endpoint.path} registered",
            )
        except (ContractUnavailable, KeyError, TypeError):
            add(
                name,
                OWNERS[endpoint.provider],
                "FAIL",
                "required endpoint/status/media contract absent",
            )
    for method, path in PARTICIPANTS:
        found = method.lower() in documents.get("transactions", {}).get("paths", {}).get(path, {})
        status = "PASS" if found else ("FAIL" if "transactions" in documents else "MISSING")
        add(path, "Aditya", status, method + " participant endpoint")
    # Every service must publish these operations; readiness itself is a real-env check.
    for service, provider in [
        ("catalog", "catalog"),
        ("orders", "transactions"),
        ("inventory", "transactions"),
        ("payments", "transactions"),
        ("analytics", "analytics"),
    ]:
        for path in ("/health/live", "/health/ready", "/metrics"):
            found = "get" in documents.get(provider, {}).get("paths", {}).get(path, {})
            add(
                service + path,
                OWNERS[provider],
                "PASS" if found else "MISSING",
                "contract registration only; service-specific readiness NOT_RUN",
            )
    for path, owner in [
        ("shared/contracts/common.py", "Jaineel / affected owners"),
        ("shared/contracts/conversation.py", "Jaineel"),
        ("shared/contracts/catalog.py", "Harsh"),
        ("shared/contracts/transactions.py", "Aditya"),
        ("shared/contracts/events.py", "Vichitr"),
        ("shared/contracts/analytics.py", "Vichitr"),
    ]:
        present = (root / path).is_file() and (root / path).stat().st_size > 0
        add(
            path,
            owner,
            "PASS" if present else "MISSING",
            "source present; runtime/provider review still required"
            if present
            else "owner implementation/DTO handoff absent",
        )
    for folder, owner, interface in [
        ("shared/outbox", "Aditya", "append_outbox(tx,event)"),
        ("shared/event_transport", "Vichitr", "build_event/validation/transport"),
        ("shared/local_diagnostics", "Vichitr", "transactional diagnostic helper"),
    ]:
        present = any(path.stat().st_size > 0 for path in (root / folder).rglob("*.py"))
        add(
            folder,
            owner,
            "UNREVIEWED" if present else "MISSING",
            interface + "; owner public binding/runtime handoff required",
        )
    for folder, owner in [
        ("contracts/events", "Vichitr"),
        ("contracts/data/catalog", "Harsh"),
        ("contracts/dictionaries/catalog", "Harsh"),
    ]:
        present = any(
            path.is_file() and path.name != ".gitkeep" for path in (root / folder).rglob("*")
        )
        # Presence alone never proves schema compatibility. Owner must supply the binding adapter.
        add(
            folder,
            owner,
            "MISSING" if not present else "UNREVIEWED",
            "event/data/dictionary schemas and compatibility binding require owner handoff",
        )
    fixtures = root / "contracts/fixtures/p2/pairs.json"
    try:
        pairs = json.loads(fixtures.read_text(encoding="utf-8"))["pairs"]
        for pair in pairs:
            endpoint = ENDPOINTS[pair["endpoint"]]
            if endpoint.provider not in documents:
                continue
            try:
                if pair.get("request") is not None:
                    contracts.validate(endpoint, "request", pair["request"])
                contracts.validate(endpoint, "response", pair["response"])
                add(
                    "example:" + pair["name"],
                    OWNERS[endpoint.provider],
                    "PASS",
                    "example validated against merged owner schema",
                )
            except ContractUnavailable:
                add(
                    "example:" + pair["name"],
                    OWNERS[endpoint.provider],
                    "MISSING",
                    "owner schema/reference unavailable",
                )
            except ContractViolation:
                add(
                    "example:" + pair["name"],
                    OWNERS[endpoint.provider],
                    "FAIL",
                    "consumed example differs from owner contract; review required",
                )
    except (OSError, ValueError, KeyError):
        add(
            "contracts/fixtures/p2/pairs.json",
            "Jaineel",
            "FAIL",
            "consumer examples missing or invalid",
        )
    return checks


def check(invocation):
    from projectctl.config import ROOT

    checks = inspect_contracts(ROOT)
    code = ExitCode.COMPLETED
    if any(item["status"] == "FAIL" for item in checks):
        code = ExitCode.CORRECTNESS_FAILURE
    elif any(item["status"] in {"MISSING", "UNREVIEWED"} for item in checks):
        code = ExitCode.DEPENDENCY_FAILURE
    reasons = tuple(
        f"{item['status']}: {item['name']} ({item['owner']}): {item['detail']}" for item in checks
    )
    return ProviderResult(
        code,
        reasons + ("Offline inventory only; G0 environment/data/locks and real smoke NOT_RUN",),
        "offline",
    )
