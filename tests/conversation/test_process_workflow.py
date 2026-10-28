"""Actual loopback HTTP and PostgreSQL; explicit provider/event doubles."""

import json
from uuid import uuid4

from .process import server


def test_network_workflow_isolation_confirmation_and_lost_response(database, context, tmp_path):
    transcript = []

    def call(client, method, path, key, body=None, *, principal=context):
        response = client.request(method, path, headers=principal.headers(key), json=body)
        transcript.append(
            {
                "method": method,
                "path": path,
                "key": key,
                "headers": principal.headers(key),
                "body": body,
                "status": response.status_code,
                "response": response.json(),
            }
        )
        (tmp_path / "http.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")
        return response

    with server(database, tmp_path / "server.log", workflow=True, lose_order_response=True) as (
        client,
        _,
        _,
    ):
        created = call(client, "POST", "/v1/sessions", "session", {})
        assert created.status_code == 201
        session = created.json()
        cart_path = "/v1/carts/" + session["cart_id"]
        assert call(client, "GET", cart_path, None).json()["version"] == 0
        other = context.model_copy(update={"user_id": "another-user"})
        assert call(client, "GET", cart_path, None, principal=other).status_code == 403
        other_namespace = context.model_copy(update={"namespace": "bench-another-audit"})
        assert call(client, "GET", cart_path, None, principal=other_namespace).status_code == 404
        turn = call(
            client,
            "POST",
            f"/v1/sessions/{session['session_id']}/turns",
            "search",
            {
                "request_id": context.request_id,
                "text": "blue cotton clothing size M",
                "mode": "fixed",
            },
        )
        assert turn.status_code == 200 and turn.json()["outcome"] == "success"
        assert turn.json()["llm_call_count"] == 0
        sku = turn.json()["products"][0]["sku"]
        edit_path = cart_path + "/items/" + sku
        edit = {"quantity": 1, "expected_cart_version": 0}
        added = call(client, "PUT", edit_path, "add", edit)
        assert added.status_code == 200
        assert call(client, "PUT", edit_path, "add", edit).json() == added.json()
        assert call(client, "PUT", edit_path, "add", {**edit, "quantity": 2}).status_code == 409
        assert call(client, "PUT", edit_path, "stale", edit).status_code == 409
        version = added.json()["version"]
        quote = call(
            client,
            "POST",
            cart_path + "/quote",
            "quote",
            {
                "expected_cart_version": version,
            },
        )
        assert quote.status_code == 201
        body = {
            "quote_id": quote.json()["quote_id"],
            "expected_cart_version": version,
            "confirmed": True,
            "confirmation_id": str(uuid4()),
        }
        edited = call(
            client,
            "PUT",
            edit_path,
            "change",
            {
                "quantity": 2,
                "expected_cart_version": version,
            },
        )
        assert edited.status_code == 200
        assert (
            call(client, "POST", cart_path + "/checkout", "old-confirmation", body).status_code
            == 409
        )
        version = edited.json()["version"]
        quote = call(
            client, "POST", cart_path + "/quote", "new-quote", {"expected_cart_version": version}
        )
        assert quote.status_code == 201
        body.update(
            quote_id=quote.json()["quote_id"],
            expected_cart_version=version,
            confirmation_id=str(uuid4()),
        )
        assert (
            call(
                client, "POST", cart_path + "/checkout", "unconfirmed", {**body, "confirmed": False}
            ).status_code
            == 422
        )
        lost = call(client, "POST", cart_path + "/checkout", "checkout", body)
        assert lost.status_code == 503 and lost.json()["error"]["details"]["outcome"] == "unknown"
        assert (
            call(
                client,
                "PUT",
                edit_path,
                "blocked-edit",
                {
                    "quantity": 3,
                    "expected_cart_version": version,
                },
            ).status_code
            == 409
        )
        accepted = call(client, "POST", cart_path + "/checkout", "checkout", body)
        assert accepted.status_code == 202 and accepted.json()["status"] == "PENDING"
        assert (
            call(client, "POST", cart_path + "/checkout", "checkout", body).json()
            == accepted.json()
        )
        assert (
            call(client, "POST", cart_path + "/checkout", "second-key", body).json()
            == accepted.json()
        )


def test_network_catalogue_failure_remains_visible(database, context, tmp_path):
    with server(database, tmp_path / "server.log", workflow=True, catalog_unavailable=True) as (
        client,
        _,
        _,
    ):
        session = client.post("/v1/sessions", headers=context.headers("session"), json={}).json()
        result = client.post(
            f"/v1/sessions/{session['session_id']}/turns",
            headers=context.headers("turn"),
            json={
                "request_id": context.request_id,
                "text": "blue clothing",
                "mode": "fixed",
            },
        )
        (tmp_path / "failure.json").write_text(
            json.dumps(result.json(), indent=2), encoding="utf-8"
        )
        assert result.status_code == 200 and result.json()["outcome"] == "dependency_error"
        assert result.json()["products"] == [] and result.json()["llm_call_count"] == 0
