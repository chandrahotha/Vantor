"""E-signature verification provenance — VNT-023, second half.

A `signed` e-signature row used to record only *when* it was confirmed, never
*on whose word*. So two very different things were the same object in the
database, in the API and in the audit chain:

* the e-sign provider confirmed the envelope, over a callback we verified; and
* a legal reviewer with `sign` authority typed the outcome into a form.

The second is a legitimate operational necessity — a provider can be
unreachable, and a migration can strand envelopes whose confirmations were never
delivered — but it is not the same claim, and a contract dispute turns on
exactly that difference. So there are now two paths and the row says which was
used.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.services import esign

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"
CALLBACK = "/api/v1/contracts/signatures/provider-callback"
SECRET = "provider-shared-secret"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "es-kid"
    from app.core import security

    security.override_jwks({"es-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="legal1", tenant="t1", roles=("Legal Reviewer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {
            "iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
            "realm_access": {"roles": list(roles)},
            "exp": now + timedelta(minutes=5), "iat": now,
        },
        pem, algorithm="RS256", headers={"kid": "es-kid"},
    )
    return {"Authorization": f"Bearer {tok}"}


def _signed_callback(body: dict, *, secret: str = SECRET, timestamp: int | None = None) -> tuple[str, str]:
    """A correctly signed callback. Returns `(body_json, signature)`."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    raw = json.dumps(body).encode()
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return raw.decode(), mac


def _open_envelope(fixture, envelope="env-abc", provider="docusign", tenant="t1"):
    """A contract in `active` with one open (pending) e-signature.

    Takes the whole `(client, pem)` fixture tuple, matching the other test
    modules here.
    """
    c, pem = fixture
    h = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    supplier = c.post("/api/v1/suppliers", json={"code": f"SUP-{envelope}", "name": "Sign Co"},
                      headers=h).json()["data"]["id"]
    contract = c.post("/api/v1/contracts", json={
        "code": f"CT-{envelope}", "title": "Supply agreement", "supplier_id": supplier,
        "start_date": "2026-01-01", "end_date": "2027-01-01", "value_minor": 100_000,
        "currency": "INR",
    }, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/contracts/{contract}/status", json={"status": "review"}, headers=h)
    c.patch(f"/api/v1/contracts/{contract}/status", json={"status": "active"},
            headers=_h(pem, sub="legal2", roles=("Legal Reviewer",)))
    signed = c.post(f"/api/v1/contracts/{contract}/sign", headers=_h(pem, sub="legal2",
                    roles=("Legal Reviewer",)),
                    json={"method": "esign", "provider": provider, "envelope_id": envelope})
    assert signed.status_code == 201, signed.text
    return contract, signed.json()["data"]["id"]


# --- the cryptography ------------------------------------------------------

def test_a_correctly_signed_callback_is_accepted(client, monkeypatch):
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    contract, _sig_id = _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed",
                                 "documentHash": "abc123"})
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"Content-Type": "application/json",
                          "X-ESign-Timestamp": str(int(time.time())),
                          "X-ESign-Signature": mac})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "signed"
    assert res.json()["data"]["verifiedVia"] == "provider_callback"


def test_the_verified_path_is_recorded_as_such(client, monkeypatch):
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    from app.core.tenant import pinned_session
    from app.models.catalog import ContractSignature
    from sqlalchemy import select

    c, _pem = client
    _contract, sig_id = _open_envelope(client, envelope="env-prov")
    raw, mac = _signed_callback({"envelope_id": "env-prov", "status": "signed"})
    assert c.post(f"{CALLBACK}?provider=docusign", content=raw,
                  headers={"X-ESign-Timestamp": str(int(time.time())),
                           "X-ESign-Signature": mac}).status_code == 200

    db = pinned_session("t1")
    try:
        row = db.execute(select(ContractSignature).where(ContractSignature.id == sig_id)).scalar_one()
        assert row.status == "signed"
        assert row.verified_via == "provider_callback"
        assert row.verified_at is not None
        # The provider's own words, kept verbatim for a dispute.
        assert row.provider_payload["envelope_id"] == "env-prov"
    finally:
        db.close()


# --- the refusals ----------------------------------------------------------

@pytest.mark.parametrize(
    "keep,label",
    [
        ([], "no credentials at all"),
        (["X-Esign-Timestamp"], "timestamp only, no signature"),
        (["X-ESign-Signature"], "signature only, no timestamp"),
    ],
    ids=["no-credentials", "no-signature", "no-timestamp"],
)
def test_an_unauthenticated_callback_is_refused(client, monkeypatch, keep, label):
    """A callback is the only unauthenticated endpoint here, so it carries all
    the risk: these are the shapes of forgery, including a well-formed body
    presented with no credentials at all."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"})
    available = {
        "X-ESign-Timestamp": str(int(time.time())),
        "X-ESign-Signature": mac,
    }
    sent = {"Content-Type": "application/json"}
    sent.update({k: v for k, v in available.items() if k in keep})
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw, headers=sent)
    assert res.status_code == 401, f"{label} -> {res.status_code}: {res.text}"


def test_a_wrong_signature_is_refused(client, monkeypatch):
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"}, secret="not-it")
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-Esign-Signature": mac})
    assert res.status_code == 401, res.text


def test_a_replayed_callback_outside_the_window_is_refused(client, monkeypatch):
    """The MAC covers a timestamp and the timestamp is checked.

    Signing the body alone makes any captured callback replayable forever: an
    attacker who observed one `signed` callback could re-send it after a later
    `voided`, or against a different envelope id.
    """
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    stale = int(time.time()) - (esign.REPLAY_WINDOW_S + 60)
    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"}, timestamp=stale)
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(stale), "X-ESign-Signature": mac})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "ESIGN_TIMESTAMP_STALE"


def test_a_future_timestamp_is_also_refused(client, monkeypatch):
    """A clock-skew allowance in one direction is a replay window in the other."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    future = int(time.time()) + (esign.REPLAY_WINDOW_S + 60)
    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"}, timestamp=future)
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(future), "X-ESign-Signature": mac})
    assert res.status_code == 401


def test_an_unconfigured_provider_is_refused_rather_than_trusted(client, monkeypatch):
    """`SECRET = ""` must never mean "verification skipped"."""
    monkeypatch.delenv("ESIGN_SECRET_DOCUSIGN", raising=False)
    c, _pem = client
    _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"}, secret="")
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-ESign-Signature": mac})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "ESIGN_PROVIDER_NOT_CONFIGURED"


def test_a_tampered_body_fails_the_mac(client, monkeypatch):
    """The MAC is computed over the bytes as received, not over a re-parse."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"})
    tampered = raw.replace('"signed"', '"voided"')
    res = c.post(f"{CALLBACK}?provider=docusign", content=tampered,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-ESign-Signature": mac})
    assert res.status_code == 401


def test_a_forged_callback_cannot_probe_for_which_envelopes_exist(client, monkeypatch):
    """Without the secret, every probe is a 401 — never a 422.

    The endpoint answers 422 for a *correctly signed* request naming an envelope
    that does not exist, because a caller who holds the shared secret has already
    proved who they are and a clear error helps them. That split is only safe if
    the 422 branch is genuinely unreachable without the secret, so this asserts
    it: an attacker gets one indistinguishable answer no matter what they guess.
    """
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    codes = set()
    messages = set()
    for envelope in ("env-abc", "env-does-not-exist", "env-guess-1", ""):
        raw, mac = _signed_callback({"envelope_id": envelope, "status": "signed"},
                                    secret="the-wrong-secret")
        res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                     headers={"X-ESign-Timestamp": str(int(time.time())),
                              "X-ESign-Signature": mac})
        codes.add(res.status_code)
        messages.add(res.json()["error"]["message"])

    assert codes == {401}, f"a forged probe was distinguishable: {codes}"
    assert len(messages) == 1, f"refusal wording leaked: {messages}"


def test_a_provider_cannot_speak_for_another_provider(client, monkeypatch):
    """The secret is per provider, so provider A's key cannot confirm B's row."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    monkeypatch.setenv("ESIGN_SECRET_ADOBE", "adobe-secret")
    c, _pem = client
    _open_envelope(client, provider="docusign")

    # Signed with the right secret, but claiming to be a different provider.
    raw, mac = _signed_callback({"envelope_id": "env-abc", "status": "signed"})
    res = c.post(f"{CALLBACK}?provider=adobe", content=raw,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-ESign-Signature": mac})
    assert res.status_code == 401


def test_a_terminal_envelope_cannot_be_flipped(client, monkeypatch):
    """`signed` then `voided` from the provider is a real dispute, not a state
    change to accept silently. The provider is authenticated here, so the refusal
    is a 422 with a real message rather than a flat 401."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client, envelope="env-term")

    def post(status):
        raw, mac = _signed_callback({"envelope_id": "env-term", "status": status})
        return c.post(f"{CALLBACK}?provider=docusign", content=raw,
                      headers={"X-ESign-Timestamp": str(int(time.time())),
                               "X-ESign-Signature": mac})

    assert post("signed").status_code == 200
    flipped = post("voided")
    assert flipped.status_code == 422
    assert flipped.json()["error"]["code"] == "ESIGN_ALREADY_TERMINAL"
    # Re-asserting the same terminal status is idempotent, not a conflict.
    assert post("signed").status_code == 200
    assert post("voided").status_code == 422


def test_a_signed_callback_for_an_unknown_envelope_is_refused(client, monkeypatch):
    """Authenticated, so a 422 with a specific message is the useful answer."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client)

    raw, mac = _signed_callback({"envelope_id": "env-does-not-exist", "status": "signed"})
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-ESign-Signature": mac})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ESIGN_ENVELOPE_NOT_FOUND"


def test_an_unmodelled_status_is_refused(client, monkeypatch):
    """A provider reporting something we do not understand must not have a value
    invented for it and written into an audited column."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    c, _pem = client
    _open_envelope(client, envelope="env-odd")

    raw, mac = _signed_callback({"envelope_id": "env-odd", "status": "wet-signed"})
    res = c.post(f"{CALLBACK}?provider=docusign", content=raw,
                 headers={"X-ESign-Timestamp": str(int(time.time())), "X-ESign-Signature": mac})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ESIGN_STATUS_UNKNOWN"


# --- provenance ------------------------------------------------------------

def test_the_operator_path_is_labelled_as_such(client, monkeypatch):
    """`POST /sign/verify` is a trusted human asserting an outcome, and now says so."""
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", SECRET)
    from app.core.tenant import pinned_session
    from app.models.catalog import ContractSignature
    from sqlalchemy import select

    c, pem = client
    _contract, sig_id = _open_envelope(client, envelope="env-manual")

    res = c.post(f"/api/v1/contracts/{_contract}/sign/verify",
                 json={"envelope_id": "env-manual", "provider": "docusign", "status": "signed"},
                 headers=_h(pem))
    assert res.status_code == 200, res.text

    db = pinned_session("t1")
    try:
        row = db.execute(select(ContractSignature).where(ContractSignature.id == sig_id)).scalar_one()
        assert row.status == "signed"
        assert row.verified_via == "manual_reconciliation", (
            "an operator-attested signature was recorded as if a provider had "
            "confirmed it")
        assert row.verified_at is not None
    finally:
        db.close()


def test_internal_signatures_are_labelled_as_clicks(client):
    from app.core.tenant import pinned_session
    from app.models.catalog import ContractSignature
    from sqlalchemy import select

    c, pem = client
    h = _h(pem, sub="mgr1", roles=("Procurement Manager",))
    supplier = c.post("/api/v1/suppliers", json={"code": "SUP-INT", "name": "Internal Co"},
                      headers=h).json()["data"]["id"]
    contract = c.post("/api/v1/contracts", json={
        "code": "CT-INT", "title": "Internal", "supplier_id": supplier,
        "start_date": "2026-01-01", "end_date": "2027-01-01",
        "value_minor": 1000, "currency": "INR"}, headers=h).json()["data"]["id"]
    c.patch(f"/api/v1/contracts/{contract}/status", json={"status": "review"}, headers=h)
    c.patch(f"/api/v1/contracts/{contract}/status", json={"status": "active"},
            headers=_h(pem, sub="legal3", roles=("Legal Reviewer",)))
    res = c.post(f"/api/v1/contracts/{contract}/sign", json={"method": "internal"},
                 headers=_h(pem, sub="legal3", roles=("Legal Reviewer",)))
    assert res.status_code == 201, res.text

    db = pinned_session("t1")
    try:
        row = db.execute(select(ContractSignature).where(
            ContractSignature.id == res.json()["data"]["id"])).scalar_one()
        assert row.method == "internal"
        assert row.verified_via == "internal_click"
    finally:
        db.close()


def test_the_database_refuses_a_signed_esign_with_no_provenance(client):
    """The invariant, enforced where it cannot be talked out of."""
    import sqlalchemy as sa
    from app.core.tenant import pinned_session
    from app.models.catalog import ContractSignature
    from sqlalchemy import select

    c, _pem = client
    contract, sig_id = _open_envelope(client, envelope="env-noprov")

    db = pinned_session("t1")
    try:
        row = db.execute(select(ContractSignature).where(ContractSignature.id == sig_id)).scalar_one()
        row.status = "signed"
        row.verified_at = datetime.now(timezone.utc)
        row.verified_via = ""  # reached `signed` with no provenance at all
        db.add(row)
        with pytest.raises(sa.exc.IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_secret_env_name_is_deterministic_and_safe(monkeypatch):
    assert esign.secret_env_name("docusign") == "ESIGN_SECRET_DOCUSIGN"
    assert esign.secret_env_name("DocuSign EU") == "ESIGN_SECRET_DOCUSIGN_EU"
    monkeypatch.setenv("ESIGN_SECRET_DOCUSIGN", "abc")
    assert esign.secret_for("docusign") == "abc"
    monkeypatch.delenv("ESIGN_SECRET_DOCUSIGN")
    assert esign.secret_for("docusign") == ""
