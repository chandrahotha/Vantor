"""Health contract — envelope shape + request-ID propagation."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_envelope_and_request_id():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["error"] is None
    assert body["requestId"]
    assert r.headers["X-Request-ID"] == body["requestId"]


def test_health_respects_incoming_request_id():
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert r.json()["requestId"] == "abc123"
