from .process import server


def test_actual_service_process_restart_preserves_cart_and_key(database, context, tmp_path):
    identity = context.headers("session")
    with server(database, tmp_path / "server.log") as (client, first_pid, _):
        created = client.post("/v1/sessions", headers=identity, json={})
        assert created.status_code == 201
        cart_id = created.json()["cart_id"]
        identity = context.headers("edit")
        path = f"/v1/carts/{cart_id}/items/FK-P6-001"
        body = {"quantity": 2, "expected_cart_version": 0}
        response = client.put(path, headers=identity, json=body)
        assert response.status_code == 200
        expected = response.json()
    with server(database, tmp_path / "server.log") as (client, second_pid, _):
        assert second_pid != first_pid
        assert client.get(f"/v1/carts/{cart_id}", headers=identity).json() == expected
        assert client.put(path, headers=identity, json=body).json() == expected
    with database.transaction() as tx:
        assert tx.execute("SELECT count(*) AS n FROM p6_test_event_capture").fetchone()["n"] == 1
