"""Security headers + CORS tests."""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _directive(csp: str, name: str) -> str:
    for part in csp.split(";"):
        part = part.strip()
        if part == name or part.startswith(name + " "):
            return part
    return ""


def test_security_headers_present():
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in r.headers
    assert "Permissions-Policy" in r.headers
    assert "Strict-Transport-Security" not in r.headers  # prod only
    # VNT-029/031: the isolation trio was two-thirds present; COEP and CORP were
    # missing, which means the page was not cross-origin isolated.
    assert r.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
    assert r.headers["Cross-Origin-Resource-Policy"] == "same-origin"


def test_content_security_policy_is_present_and_strict():
    """VNT-031: there was no CSP at all, and the docstring said so.

    A policy nobody writes down never gets reviewed, and this one has to be
    judged on what it actually forbids, not on whether the header exists.
    """
    csp = client.get("/api/v1/health").headers["Content-Security-Policy"]
    assert csp, "no Content-Security-Policy was sent"

    # The two that make an injected tag inert regardless of script execution.
    assert _directive(csp, "object-src") == "object-src 'none'"
    assert _directive(csp, "base-uri") == "base-src" or _directive(csp, "base-uri") == "base-uri 'none'"
    # Clickjacking defence at the CSP layer.
    assert _directive(csp, "frame-ancestors") == "frame-ancestors 'none'"

    script = _directive(csp, "script-src")
    assert script, "script-src must be explicit"
    # `unsafe-inline` in script-src is the thing that makes a CSP decorative.
    assert "'unsafe-inline'" not in script, f"script-src permits inline script: {script}"
    # A nonce plus strict-dynamic is how a framework that emits inline bootstrap
    # scripts is allowed to keep working without unsafe-inline.
    assert "'nonce-" in script
    assert "'strict-dynamic'" in script

    assert _directive(csp, "default-src") == "default-src 'self'"
    assert _directive(csp, "form-action") == "form-action 'self'"
    connect = _directive(csp, "connect-src")
    assert "'self'" in connect
    # The API origin must be explicitly allowed or the app cannot talk to it.
    assert "http://localhost:8000" in connect


def test_csp_nonce_is_fresh_per_response():
    """A reused nonce is not a nonce — it becomes a static allowance."""
    first = client.get("/api/v1/health").headers["Content-Security-Policy"]
    second = client.get("/api/v1/health").headers["Content-Security-Policy"]
    nonce = lambda csp: _directive(csp, "script-src").split("'nonce-")[1].split("'")[0]  # noqa: E731
    assert nonce(first) != nonce(second)
    assert len(nonce(first)) >= 20


def test_report_only_is_sent_outside_production():
    """A stricter policy has to be triallable without breaking the app.

    Compared with the nonce stripped: both headers are built from the same policy
    but each response mints its own nonce, so byte equality is not the assertion —
    "same policy, different nonce" is.
    """
    r = client.get("/api/v1/health")
    enforcing = r.headers["Content-Security-Policy"]
    report_only = r.headers.get("Content-Security-Policy-Report-Only")
    assert report_only, "no report-only policy outside production"
    strip = lambda csp: re.sub(r"'nonce-[^']+'", "'nonce-X'", csp)  # noqa: E731
    assert strip(report_only) == strip(enforcing)


def test_cors_allowlisted_origin():
    r = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert r.headers["Access-Control-Allow-Credentials"] == "true"


def test_cors_allows_the_byok_header():
    """The copilot sends a per-request provider key; CORS must permit it."""
    r = client.options("/api/v1/ai/complete", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert "X-Vantor-Provider-Key" in r.headers["Access-Control-Allow-Headers"]


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
