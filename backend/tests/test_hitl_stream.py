"""HITL + streaming tests — approval filing/decide, SSE framing."""
import json as json_mod
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.services.ai_gateway import AIGatewayError

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
    # double-decide is a conflict, not a validation error: the request is
    # well-formed but the resource has already moved on.
    assert c.post(f"/api/v1/ai/approvals/{aid}/decide", json={"approve": False}, headers=mgr).status_code == 409
    # a rejection must carry a written reason
    other = c.post("/api/v1/ai/tools/request_approval",
                   json={"action": "award_contract", "resource": "rfq", "resource_id": "rfq-2"},
                   headers=_h(pem, "filer2")).json()["data"]["result"]["approval_id"]
    assert c.post(f"/api/v1/ai/approvals/{other}/decide", json={"approve": False},
                  headers=mgr).status_code == 422
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
    # VNT-014: the disabled path is a refusal frame, not an answer frame. It is
    # emitted before any token because a stream cannot un-send what it has already
    # written to the client, so the decision has to come first.
    assert "AI_NO_EVIDENCE" in r.text
    assert '"grounded": false' in r.text or '"grounded":false' in r.text
    # The disabled path is one complete frame, flagged as not live-streamed so a
    # client cannot mistake it for token streaming.
    assert '"streamed": false' in r.text or '"streamed":false' in r.text
    # And the refusal is audited: an unpinned session is rejected by the
    # audit_events RLS policy on Postgres, which used to drop the write silently.
    feed = c.get("/api/v1/audit-events?action=AI_REFUSED", headers=_h(pem)).json()["data"]
    assert any(e["action"] == "AI_REFUSED" for e in feed), feed


def test_stream_framing_live_provider(monkeypatch, client):
    """The endpoint must emit provider deltas as they arrive, not slice a finished
    response. This is the regression that made `/ai/stream` theatre."""
    c, pem = client

    def fake_stream(*, prompt, system="", provider="", provider_key="", model="",
                    grounding="", evidence=None):
        yield "hel"
        yield "lo "
        yield "supplier"
        yield "s"

    monkeypatch.setattr("app.services.ai_gateway.stream", fake_stream)
    monkeypatch.setattr("app.services.ai_gateway.complete", lambda **kw: {"answer": ""})  # not reached

    # A tool is supplied so the turn is groundable: since VNT-014 an ungrounded
    # stream is refused before its first token, which would make this test pass
    # without ever exercising the delta framing it is about.
    c.post("/api/v1/suppliers", json={"code": "SUP-ST", "name": "Stream Co"}, headers=_h(pem))
    r = c.post("/api/v1/ai/stream", json={"prompt": "Hello", "provider": "ollama",
                                          "tools": [{"name": "search_suppliers",
                                                     "args": {"q": "Stream Co", "limit": 5}}]},
               headers=_h(pem))
    assert r.status_code == 200
    frames = [json_mod.loads(l[5:]) for l in r.text.split("\n\n") if l.startswith("data: ") and not l.startswith("data: [EVIDENCE]")]
    assert "".join(f["delta"] for f in frames) == "hello suppliers"
    assert all(f["streamed"] for f in frames)
    assert "[EVIDENCE]" in r.text
    assert "AI_NO_EVIDENCE" not in r.text


def test_stream_passes_the_tool_results_to_the_model(monkeypatch, client):
    """The model must actually be shown the evidence the response cites.

    This is the one that matters for the product's central claim. The streaming
    path - the one the copilot uses - computed `grounding` and then did not pass
    it to the provider, while the non-streaming path always had. The answer was
    therefore produced *without* the tenant's data and then shipped with evidence
    chips and a confidence number implying otherwise: a confident, cited-looking
    answer to a question the model had never been given the data for.

    Nothing caught it because the framing tests only asserted on the deltas and
    the presence of an `[EVIDENCE]` frame - both of which were fine. The bug was
    in what reached the model, which nothing looked at.
    """
    c, pem = client
    seen: dict = {}

    def fake_stream(*, prompt, system="", provider="", provider_key="", model="",
                    grounding="", evidence=None):
        seen["prompt"] = prompt
        seen["grounding"] = grounding
        seen["evidence"] = evidence
        yield "ack"

    monkeypatch.setattr("app.services.ai_gateway.stream", fake_stream)

    c.post("/api/v1/suppliers", json={"code": "SUP-GR", "name": "Grounded Co"}, headers=_h(pem))
    r = c.post("/api/v1/ai/stream", json={"prompt": "Who is Grounded Co?", "provider": "ollama",
                                          "tools": [{"name": "search_suppliers",
                                                     "args": {"q": "Grounded Co", "limit": 5}}]},
               headers=_h(pem))
    assert r.status_code == 200
    assert "[EVIDENCE]" in r.text, "the turn was not groundable, so the test proves nothing"

    # The tool's rows are in what the model was asked.
    assert seen["grounding"], "grounding was computed but never passed to the model"
    assert "Grounded Co" in seen["grounding"]
    assert seen["evidence"], "evidence was collected but never passed to the model"
    # And the user prompt is fenced, so tool output cannot pose as instructions.
    assert "Grounded Co" in seen["prompt"]


def test_stream_provider_error_is_explicit(monkeypatch, client):
    """A live provider failure must surface as an error event, never fake text."""
    c, pem = client

    def boom(*, prompt, system="", provider="", provider_key="", model="",
             grounding="", evidence=None):
        raise AIGatewayError("ollama", "stream failed: connection refused")
        return
        yield

    monkeypatch.setattr("app.services.ai_gateway.stream", boom)
    r = c.post("/api/v1/ai/stream", json={"prompt": "Hello", "provider": "ollama"}, headers=_h(pem))
    assert r.status_code == 200  # SSE stays 200; failures are error *events*
    assert '"error"' in r.text and "ollama" in r.text
