"""Replayable P7 API smoke; captured IDs and explicit dependency-double opt-in."""

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from shared.contracts.common import RequestContext


@contextmanager
def test_client():
    """Only reached with --test-double-providers; PostgreSQL is still real."""
    import psycopg
    from fastapi.testclient import TestClient
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from services.conversation.app import create_app
    from services.conversation.database import Database
    from services.conversation.state import ConversationState
    from services.conversation.workflow import FixedWorkflow
    from tests.conversation.doubles import EventCaptureDouble
    from tests.conversation.workflow_doubles import WorkflowProviderDouble

    url = os.environ.get("P6_TEST_DATABASE_URL")
    if not url:
        raise ValueError("P6_TEST_DATABASE_URL required; no database fallback")
    schema = "p7_smoke_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    database = Database(make_conninfo(url, options=f"-c search_path={schema}"))
    try:
        database.migrate()
        EventCaptureDouble.install(database)
        state = ConversationState(database, events=EventCaptureDouble())
        provider = WorkflowProviderDouble()
        workflow = FixedWorkflow(state, provider.gateway())
        with TestClient(
            create_app(state=state, workflow=workflow, mode="stub", purpose="contract_test")
        ) as client:
            yield client, provider
    finally:
        assert schema.startswith("p7_smoke_") and len(schema) == 41
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def exercise(client, provider, out, query, *, confirm):
    context = RequestContext(
        namespace="bench-p7-" + uuid4().hex,
        run_id=str(uuid4()),
        user_id="p7-synthetic-smoke",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
    transcript, assertions = [], []

    def check(name, passed):
        assertions.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    def call(method, path, key, body=None):
        response = client.request(method, path, headers=context.headers(key), json=body)
        transcript.append(
            {
                "method": method,
                "path": path,
                "key": key,
                "body": body,
                "status": response.status_code,
                "response": response.json(),
            }
        )
        (out / "http.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
        return response

    def search(text, key):
        nonlocal context
        context = context.model_copy(update={"request_id": str(uuid4())})
        return call(
            "POST",
            f"/v1/sessions/{session['session_id']}/turns",
            key,
            {"request_id": context.request_id, "text": text, "mode": "fixed"},
        )

    try:
        created = call("POST", "/v1/sessions", "session", {})
        check("session_created", created.status_code == 201)
        session = created.json()
        context = context.model_copy(update={"session_id": session["session_id"]})
        result = search(query, "search")
        check("fixed_search", result.status_code == 200 and result.json()["outcome"] == "success")
        check(
            "model_not_called",
            result.json()["llm_call_count"] == 0 and result.json()["timings_ms"]["llm"] is None,
        )
        products = result.json()["products"]
        check("returned_product_required", bool(products))
        sku = products[0]["sku"]
        unknown = search("clothing size XXXXXL", "unknown")
        check("unsupported_size_clarifies", unknown.json()["outcome"] == "clarification")
        cart_id = session["cart_id"]
        edit_path = f"/v1/carts/{cart_id}/items/{sku}"
        add = call("PUT", edit_path, "add", {"quantity": 1, "expected_cart_version": 0})
        check("cart_added", add.status_code == 200)
        version = add.json()["version"]
        quote = call(
            "POST", f"/v1/carts/{cart_id}/quote", "quote", {"expected_cart_version": version}
        )
        check("quote_returned", quote.status_code == 201)
        quote = quote.json()
        check(
            "quote_bound_to_cart", quote["cart_id"] == cart_id and quote["cart_version"] == version
        )
        confirmation = {
            "quote_id": quote["quote_id"],
            "expected_cart_version": version,
            "confirmed": True,
            "confirmation_id": str(uuid4()),
        }
        changed = call(
            "PUT", edit_path, "edit-after-quote", {"quantity": 2, "expected_cart_version": version}
        )
        check("cart_edited", changed.status_code == 200)
        stale = call("POST", f"/v1/carts/{cart_id}/checkout", "stale", confirmation)
        check("stale_confirmation_rejected", stale.status_code == 409)
        version = changed.json()["version"]
        quote = call(
            "POST", f"/v1/carts/{cart_id}/quote", "new-quote", {"expected_cart_version": version}
        ).json()
        if confirm:
            confirmation = {
                "quote_id": quote["quote_id"],
                "expected_cart_version": version,
                "confirmed": True,
                "confirmation_id": str(uuid4()),
            }
            if provider is not None:
                provider.lose_order_response = True
                lost = call("POST", f"/v1/carts/{cart_id}/checkout", "checkout", confirmation)
                check(
                    "lost_response_unknown",
                    lost.status_code == 503
                    and lost.json()["error"]["details"]["outcome"] == "unknown",
                )
            accepted = call("POST", f"/v1/carts/{cart_id}/checkout", "checkout", confirmation)
            check("checkout_accepted", accepted.status_code == 202)
            repeated = call("POST", f"/v1/carts/{cart_id}/checkout", "checkout", confirmation)
            check("same_order_on_retry", repeated.json() == accepted.json())
            if provider is not None:
                check("one_double_order", len(provider.accepted) == 1)
                check("accepted_is_pending", accepted.json()["status"] == "PENDING")
                check("zero_model_attempts", provider.model.attempts == 0)
        summary = {
            "status": "PASS",
            "provider_mode": "explicit_http_double" if provider else "real",
            "database": "real PostgreSQL",
            "assertions": assertions,
            "live_assist": "NOT_RUN",
            "real_G3": "NOT_RUN",
        }
    except Exception:
        summary = {"status": "FAIL", "assertions": assertions}
        raise
    finally:
        (out / "smoke.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{len(assertions)}/{len(assertions)} assertions pass; {out / 'smoke.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--test-double-providers", action="store_true")
    choice.add_argument("--base-url")
    parser.add_argument("--query", default="clothing")
    parser.add_argument(
        "--confirm-checkout",
        action="store_true",
        help="explicitly submit the displayed simulated quote",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.test_double_providers:
        with test_client() as (client, provider):
            exercise(client, provider, args.out, args.query, confirm=args.confirm_checkout)
    else:
        from services.conversation.clients import TransportConfig

        TransportConfig(args.base_url)  # reject credentials/paths and non-HTTP URLs
        with httpx.Client(base_url=args.base_url, timeout=5, trust_env=False) as client:
            exercise(client, None, args.out, args.query, confirm=args.confirm_checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
