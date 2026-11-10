"""Demo through a real M1 process/PostgreSQL; explicit catalogue/Orders doubles."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from projectctl.demo import run
from tests.projectctl.test_demo import arguments, resume

from .process import server


@pytest.mark.parametrize("terminal", ["CONFIRMED", "CANCELLED"])
def test_demo_real_m1_persistence_http_and_response_loss(database, tmp_path, terminal):
    state_path = tmp_path / "client.json"
    polls, output = [], []
    with server(database, tmp_path / "m1.log", workflow=True, lose_order_response=True) as (
        network,
        _,
        _,
    ):

        def route(request):
            if request.url.path.startswith("/v1/orders/"):
                # Orders finality is explicitly doubled; it is not a saga pass.
                state = json.loads(state_path.read_text())
                quote = state["quote"]
                polls.append(request)
                now = datetime.now(UTC).isoformat()
                value = {
                    "order_id": state["order_id"],
                    "quote_id": quote["quote_id"],
                    "session_id": state["session_id"],
                    "user_id": state["identity"]["user_id"],
                    "status": terminal,
                    "order_version": 3,
                    "lines": quote["lines"],
                    "total_amount_minor": quote["total_amount_minor"],
                    "currency": quote["currency"],
                    "reservation_id": None,
                    "payment_id": None,
                    "failure_code": "DECLINED" if terminal == "CANCELLED" else None,
                    "created_at": now,
                    "updated_at": now,
                }
                return httpx.Response(200, json=value)
            response = network.request(
                request.method,
                request.url.path,
                headers=dict(request.headers),
                content=request.content,
            )
            return httpx.Response(
                response.status_code, content=response.content, headers=dict(response.headers)
            )

        def ask(prompt):
            if "Select product" in prompt or "Quantity" in prompt:
                return "1"
            if "Type CONFIRM" in prompt:
                state = json.loads(state_path.read_text())
                assert state["phase"] == "confirm" and not any(
                    name.startswith("checkout:") for name in state["operations"]
                )
                return "CONFIRM " + state["quote"]["quote_id"]
            raise AssertionError("unexpected prompt: " + prompt)

        with httpx.Client(transport=httpx.MockTransport(route)) as client:
            assert (
                run(
                    arguments(state_path, "--query", "blue cotton clothing size M"),
                    ask=ask,
                    tell=output.append,
                    client=client,
                )
                == 0
            )
            assert (
                run(
                    resume(state_path),
                    ask=lambda _: pytest.fail("completed run prompted"),
                    tell=output.append,
                    client=client,
                )
                == 0
            )
        state = json.loads(state_path.read_text())
        assert state["final_status"] == terminal and len(polls) == 1
        with database.transaction() as tx:
            assert tx.execute("SELECT count(*) AS n FROM confirmations").fetchone()["n"] == 1
            assert (
                tx.execute(
                    "SELECT count(*) AS n FROM workflow_commands "
                    "WHERE operation='checkout_cart' AND state='complete'"
                ).fetchone()["n"]
                == 1
            )
            stored = tx.execute("SELECT response FROM turns").fetchone()["response"]
            assert stored["llm_call_count"] == 0
        rows = [
            json.loads(line)
            for line in state_path.with_suffix(".json.http.jsonl").read_text().splitlines()
        ]
        checkouts = [row for row in rows if row["phase"] == "request" and row["kind"] == "checkout"]
        assert len(checkouts) == 2  # M1 returned 503 after an accepted provider response was lost
        assert checkouts[0]["headers"] == checkouts[1]["headers"]
        assert checkouts[0]["body"] == checkouts[1]["body"]
        assert any("TOTAL: INR 399.00" in line for line in output)
