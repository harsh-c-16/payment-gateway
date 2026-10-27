"""Replayable P6 checkpoint: real PostgreSQL + explicit test event/outbox capture.

Never use this as a real shared-outbox/Kafka or P7 workflow integration result.
Creates a fresh isolated test schema and retains it for --resume/restart checks.
"""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from services.conversation.database import Database
from services.conversation.errors import ServiceError
from services.conversation.state import ConversationState
from shared.contracts.common import RequestContext
from shared.contracts.conversation import CartUpdateRequest
from tests.conversation.doubles import EventCaptureDouble
from tests.conversation.process import server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("P6_TEST_DATABASE_URL")
    if not url:
        print("NOT_RUN: P6_TEST_DATABASE_URL required; no database fallback.")
        return 4
    if args.resume:
        saved = json.loads((args.out / "smoke.json").read_text(encoding="utf-8"))
        schema = saved["schema"]
        context = RequestContext.model_validate(saved["context"])
    else:
        args.out.mkdir(parents=True, exist_ok=False)
        schema = "p6_smoke_" + uuid4().hex
        context = RequestContext(
            namespace="bench-p6-" + uuid4().hex,
            run_id=str(uuid4()),
            user_id="p6-synthetic-smoke-user",
            correlation_id=str(uuid4()),
            request_id=str(uuid4()),
            session_id=None,
        )
    if not schema.startswith("p6_smoke_") or len(schema) != 41 or not schema[9:].isalnum():
        raise ValueError("only an isolated P6 smoke schema is allowed")
    database = Database(make_conninfo(url, options=f"-c search_path={schema}"))
    if not args.resume:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        database.migrate()
        EventCaptureDouble.install(database)
    transcript = []
    assertions = []

    def call(client, method, path, *, key=None, body=None, principal=None):
        identity = context.headers(key)
        if principal:
            identity["X-User-ID"] = principal
        response = client.request(method, path, headers=identity, json=body)
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
        return response

    def check(name, passed):
        assertions.append({"name": name, "passed": bool(passed)})
        if not passed:
            raise AssertionError(name)

    try:
        if args.resume:
            with server(database, args.out / "server.log") as (client, pid, command):
                response = call(client, "GET", f"/v1/carts/{saved['created']['cart_id']}")
                check("cart_survives_postgresql_restart", response.json() == saved["snapshot"])
                replay = call(
                    client, "PUT", saved["edit_path"], key="edit", body=saved["edit_body"]
                )
                check(
                    "original_key_survives_postgresql_restart", replay.json() == saved["snapshot"]
                )
            with database.transaction() as tx:
                check(
                    "one_test_event_after_database_restart",
                    tx.execute("SELECT count(*) AS n FROM p6_test_event_capture").fetchone()["n"]
                    == 1,
                )
            result = {
                "mode": "real-postgresql/test-double-events",
                "checks": assertions,
                "requests": transcript,
                "server_pid": pid,
                "command": command,
            }
            (args.out / "database-restart.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            print(args.out / "database-restart.json")
            return 0
        with server(database, args.out / "server.log") as (client, first_pid, first_command):
            first = call(client, "POST", "/v1/sessions", key="session", body={})
            check("session_created", first.status_code == 201)
            created = first.json()
            replay = call(client, "POST", "/v1/sessions", key="session", body={})
            check("session_key_replays", replay.json() == created)
            edit_path = f"/v1/carts/{created['cart_id']}/items/FK-P6-SMOKE"
            edit_body = {"quantity": 1, "expected_cart_version": 0}
            first = call(client, "PUT", edit_path, key="edit", body=edit_body)
            check("cart_added", first.status_code == 200)
            snapshot = first.json()
            replay = call(client, "PUT", edit_path, key="edit", body=edit_body)
            check("edit_key_replays", replay.json() == snapshot)
            changed = call(client, "PUT", edit_path, key="edit", body={**edit_body, "quantity": 2})
            check(
                "changed_input_conflicts",
                changed.status_code == 409
                and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT",
            )
            stale = call(client, "PUT", edit_path, key="stale", body=edit_body)
            check(
                "old_cart_version_conflicts",
                stale.status_code == 409
                and stale.json()["error"]["code"] == "CART_VERSION_CONFLICT",
            )
            other = call(client, "GET", f"/v1/carts/{created['cart_id']}", principal="other")
            check("other_principal_rejected", other.status_code == 403)
        with server(database, args.out / "server.log") as (client, second_pid, second_command):
            check("service_process_restarted", first_pid != second_pid)
            response = call(client, "GET", f"/v1/carts/{created['cart_id']}")
            check("cart_survives_service_restart", response.json() == snapshot)
            replay = call(client, "PUT", edit_path, key="edit", body=edit_body)
            check("original_key_survives_service_restart", replay.json() == snapshot)
        failing = ConversationState(database, events=EventCaptureDouble(fail_after_append=True))
        try:
            failing.update_cart(
                created["cart_id"],
                "FK-P6-SMOKE",
                CartUpdateRequest(quantity=2, expected_cart_version=1),
                context,
                "rollback",
            )
        except ServiceError:
            pass
        else:
            raise AssertionError("injected failure did not occur")
        actual = ConversationState(database, events=EventCaptureDouble()).get_cart(
            created["cart_id"], context
        )
        check("cart_effect_rolls_back", actual.model_dump(mode="json") == snapshot)
        with database.transaction() as tx:
            captured = tx.execute(
                "SELECT event FROM p6_test_event_capture ORDER BY aggregate_version"
            ).fetchall()
            check("test_outbox_capture_rolls_back", len(captured) == 1)
            check(
                "idempotency_key_rolls_back",
                tx.execute(
                    "SELECT count(*) AS n FROM operation_keys WHERE key='rollback'"
                ).fetchone()["n"]
                == 0,
            )
            version = tx.execute("SELECT version() AS version").fetchone()["version"]
        result = {
            "mode": "real-postgresql/test-double-events",
            "schema": schema,
            "shared_event_path": "NOT_RUN",
            "p7": "NOT_RUN",
            "database_version": version,
            "context": context.model_dump(mode="json"),
            "created": created,
            "snapshot": snapshot,
            "edit_path": edit_path,
            "edit_body": edit_body,
            "checks": assertions,
            "requests": transcript,
            "captured_test_events": captured,
            "server_pids": [first_pid, second_pid],
            "commands": [first_command, second_command],
        }
        (args.out / "smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        # Partial failed requests/assertions remain visible too; no schema is dropped.
        (args.out / ("resume-transcript.json" if args.resume else "transcript.json")).write_text(
            json.dumps({"assertions": assertions, "requests": transcript}, indent=2),
            encoding="utf-8",
        )
    print(args.out / "smoke.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
