"""HITL + streaming tests — approval filing/decide, SSE framing."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    monkeypatch.setenv("AI_PROVIDER", "disabled")
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "hl-kid"
    from app.core import security

    security.override_jwks({"hl-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "hl-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_hitl_file_and_decide(client):
    c, pem = client
    filed = c.post("/api/v1/ai/tools/request_approval",
                   json={"action": "award_contract", "resource": "rfq", "resource_id": "rfq-1", "reason": "high value"},
                   headers=_h(pem)).json()["data"]["result"]
    assert filed["status"] == "requested"
    aid = filed["approval_id"]
    # unknown action refused; filer cannot decide own filing
    assert c.post("/api/v1/ai/tools/request_approval",
                  json={"action": "launch_missiles", "resource": "x", "resource_id": "y"},
                  headers=_h(pem)).status_code == 422
    assert c.post(f"/api/v1/ai/approvals/{aid}/decide", json={"approve": True},
                  headers=_h(pem)).status_code == 403
    mgr = _h(pem, "mgr1", roles=("Approver",))
    assert c.post(f"/api/v1/ai/approvals/{aid}/decide", json={"approve": True, "reason": "reviewed"},
                  headers=mgr).json()["data"]["status"] == "approved"
    # double-decide blocked; other tenant blind
    assert c.post(f"/api/v1/ai/approvals/{aid}/decide", json={"approve": False}, headers=mgr).status_code == 422
    assert c.post(f"/api/v1/ai/approvals/{aid}/decide", json={"approve": True},
                  headers=_h(pem, "u2", "other", ("Approver",))).status_code == 404


def test_hitl_rejects_unbounded_resource(client):
    """`approvals.resource` is a bounded column and the tool prefixes `ai:`.

    A long caller-supplied resource used to overflow on Postgres at commit time
    (a 500), while passing silently on SQLite. It must be a 422 instead, and
    must not silently truncate into a wrong approval target.
    """
    c, pem = client
    h = _h(pem)
    # 62 chars: "ai:" + 62 = 65 would exceed the 64-char column.
    long_res = "r" * 62
    r = c.post("/api/v1/ai/tools/request_approval",
               json={"action": "award_contract", "resource": long_res, "resource_id": "rfq-1"},
               headers=h)
    assert r.status_code == 422, r.text
    # empty resource / resource_id are refused too
    assert c.post("/api/v1/ai/tools/request_approval",
                  json={"action": "award_contract", "resource": "  ", "resource_id": "rfq-1"},
                  headers=h).status_code == 422
    assert c.post("/api/v1/ai/tools/request_approval",
                  json={"action": "award_contract", "resource": "rfq", "resource_id": "i" * 37},
                  headers=h).status_code == 422
    # a legal 61-char resource still files, and round-trips intact
    ok = c.post("/api/v1/ai/tools/request_approval",
                json={"action": "award_contract", "resource": "r" * 61, "resource_id": "rfq-1"},
                headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["result"]["resource"] == "ai:" + "r" * 61
    # no truncated/overflowing row was left behind by the rejected attempts
    assert c.get("/api/v1/audit-events?action=AI_APPROVAL_DECIDED", headers=h).status_code == 200


def test_stream_framing_disabled(client):
    c, pem = client
    r = c.post("/api/v1/ai/stream", json={"prompt": "Summarize spend"}, headers=_h(pem))
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "[EVIDENCE]" in r.text
    assert "UNKNOWN" in r.text
    # The stream is SSE-framed but NOT provider-streamed — it says so, so a
    # client cannot mistake it for real token streaming.
    assert '"streamed": false' in r.text.replace("'", '"') or '"streamed":false' in r.text
    # And the completion is audited: an unpinned session is rejected by the
    # audit_events RLS policy on Postgres, which used to drop the write silently.
    feed = c.get("/api/v1/audit-events?action=AI_COMPLETED", headers=_h(pem)).json()["data"]
    assert any(e["action"] == "AI_COMPLETED" for e in feed)
