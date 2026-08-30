from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}


def test_health_has_request_id_header(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"]


def test_health_no_auth_required(client: TestClient) -> None:
    resp = client.get("/api/v1/health", headers={})
    assert resp.status_code == 200


def test_protected_endpoint_unauthenticated_error_envelope(
    client_raw_no_override: TestClient,
) -> None:
    resp = client_raw_no_override.post("/api/v1/goals", json={"title": "x"}, headers={})
    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["error"]["message"]
    assert "request_id" in body["error"]
    assert isinstance(body["error"]["details"], dict)
