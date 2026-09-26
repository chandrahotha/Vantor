"""Security headers + CORS tests."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_security_headers_present():
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in r.headers
    assert "Permissions-Policy" in r.headers
    assert "Strict-Transport-Security" not in r.headers  # prod only


def test_cors_allowlisted_origin():
    r = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert r.headers["Access-Control-Allow-Credentials"] == "true"


def test_cors_evil_origin_gets_nothing():
    r = client.get("/api/v1/health", headers={"Origin": "https://evil.test"})
    assert "Access-Control-Allow-Origin" not in r.headers


def test_preflight_short_circuit():
    r = client.options("/api/v1/suppliers", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 204
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Authorization" in r.headers["Access-Control-Allow-Headers"]
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Request-ID"] != ""


def test_preflight_evil_origin_refused():
    r = client.options("/api/v1/suppliers", headers={
        "Origin": "https://evil.test", "Access-Control-Request-Method": "POST"})
    assert r.status_code in (404, 405)  # falls through, no CORS grant
    assert "Access-Control-Allow-Origin" not in r.headers


def test_error_responses_still_hardened():
    r = client.get("/api/v1/suppliers/does-not-exist")
    assert r.status_code == 401  # auth first, still enveloped + hardened
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Request-ID"] == r.json()["requestId"]
