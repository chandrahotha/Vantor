"""Health contract — envelope shape + request-ID propagation."""
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

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
    # VNT-030. An inbound id used to be echoed verbatim with no length bound and
    # no character class, and it lands in the response header and every JSON body.
    # A short, well-formed id is still honoured so a caller's correlation id
    # survives; anything else is replaced rather than rejected, because refusing a
    # request over a malformed log field would trade a logging concern for an
    # availability one.
    assert r.json()["requestId"] == "abc123", r.text


def test_malformed_request_ids_are_replaced_not_reflected():
    """The injection vector: control characters and unbounded length."""
    from app.core.errors import REQUEST_ID_MAX, sanitize_request_id

    for hostile in (
        "abc\r\nX-Injected: yes",
        "abc\ndef",
        "x" * (REQUEST_ID_MAX + 1),
        "has space",
        "",
        "!!!",
    ):
        got = sanitize_request_id(hostile)
        assert got != hostile or not hostile
        assert len(got) <= REQUEST_ID_MAX
        assert "\n" not in got and "\r" not in got

    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc\r\nX-Injected: yes"})
    assert r.status_code == 200
    # The header value is whatever the sanitiser produced, never the raw input.
    assert "\n" not in r.headers["X-Request-ID"]
    assert "X-Injected" not in r.headers.get("X-Request-ID", "")
    assert r.json()["requestId"] == r.headers["X-Request-ID"]


def _tok(roles):
    """Mint a real RS256 token whose key is registered for this test only."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    k = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "ops-test-kid"
    from app.core import security

    security.override_jwks({"ops-test-kid": RSAAlgorithm.from_jwk(jwk)})
    now = datetime.now(timezone.utc)
    return jwt.encode({"iss": "https://issuer.test/realms/vantor", "aud": "vantor-web",
                       "sub": "u", "tenant_id": "t1", "realm_access": {"roles": roles},
                       "exp": now + timedelta(minutes=5), "iat": now},
                      k, algorithm="RS256", headers={"kid": "ops-test-kid"})


def test_ops_metrics_is_role_gated():
    from app.core import security

    assert client.get("/api/v1/ops/metrics").status_code == 401
    client.get("/api/v1/ops/metrics", headers={"Authorization": f"Bearer {_tok(['Buyer'])}"}).status_code == 403
    r = client.get("/api/v1/ops/metrics", headers={"Authorization": f"Bearer {_tok(['Auditor'])}"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert set(d) == {"process", "requests", "latency"}
    assert "p95Ms" in d["latency"] and "uptimeSeconds" in d["process"]
    security.override_jwks(None)
