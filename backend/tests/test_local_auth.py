"""Local, passwordless sign-in.

The point of these tests is that "passwordless" loosened exactly one thing —
who may ask for a session — and nothing else. The token is still RS256, still
signed by a key only the server holds, still carries a tenant, still expires,
and is still verified on the same code path a federated token takes. A forged
token is still a 401.

They also pin the removal of `DISABLE_AUTH=1`, which used to hand out a
full-Admin actor with no token at all, in every environment, from a module whose
docstring said "No dev bypass, no hardcoded tokens, no anon-auth flag".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.test/realms/vantor")
    monkeypatch.setenv("JWT_AUDIENCE", "vantor-web")
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("LOCAL_KEY_PATH", str(tmp_path / "signing-key.pem"))
    from app.core import localauth
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    localauth.reset_cache()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.main import app as fastapi_app

    yield TestClient(fastapi_app, raise_server_exceptions=False)

    Base.metadata.drop_all(engine)
    reset_engine_cache()
    localauth.reset_cache()
    get_settings.cache_clear()


def _token(c: TestClient) -> str:
    r = c.post("/api/v1/auth/session")
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def test_a_session_is_a_real_signed_token_with_a_tenant(client):
    body = client.post("/api/v1/auth/session").json()["data"]
    claims = jwt.decode(body["token"], options={"verify_signature": False})
    assert claims["tenant_id"] == "vantor-corp"
    assert claims["iss"] == "https://issuer.test/realms/vantor"
    assert claims["aud"] == "vantor-web"
    assert claims["exp"] > claims["iat"]
    assert "Buyer" in claims["realm_access"]["roles"]
    # Marks how the session was obtained, so the audit trail can distinguish a
    # passwordless local session from a federated identity.
    assert claims["vantor_auth"] == "local"
    assert body["expiresIn"] > 0
    assert body["user"]["tenant"] == "vantor-corp"


def test_the_session_opens_the_rest_of_the_api(client):
    h = {"Authorization": f"Bearer {_token(client)}"}
    assert client.get("/api/v1/suppliers", headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).json()["data"]["authSource"] == "local"


def test_the_token_is_signed_and_not_merely_asserted(client):
    """Passwordless issuance must not mean unverified acceptance."""
    good = _token(client)
    head, payload, sig = good.split(".")
    # Flip the signature: same claims, wrong signer.
    forged = f"{head}.{payload}.{'A' * len(sig)}"
    assert client.get("/api/v1/suppliers", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/api/v1/suppliers", headers={"Authorization": "Bearer vantor-admin"}).status_code == 401
    assert client.get("/api/v1/suppliers").status_code == 401


def test_a_token_signed_by_someone_else_is_refused(client):
    """An attacker who knows the claim shape still cannot mint a session."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.core import localauth

    theirs = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = theirs.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {
            "iss": "https://issuer.test/realms/vantor",
            "aud": "vantor-web",
            "sub": "attacker",
            "tenant_id": "vantor-corp",
            "realm_access": {"roles": ["Super Admin"]},
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        pem,
        algorithm="RS256",
        # Claiming the local kid is the interesting case: the server must check
        # the signature against its own key, not trust the header.
        headers={"kid": localauth.LOCAL_KID},
    )
    assert client.get("/api/v1/suppliers", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_an_expired_session_is_refused(client):
    from app.core import localauth

    key = localauth.signing_key()
    from cryptography.hazmat.primitives import serialization

    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    tok = jwt.encode(
        {
            "iss": "https://issuer.test/realms/vantor",
            "aud": "vantor-web",
            "sub": "local-operator",
            "tenant_id": "vantor-corp",
            "realm_access": {"roles": ["Buyer"]},
            "iat": past,
            "exp": past + timedelta(minutes=1),
        },
        pem,
        algorithm="RS256",
        headers={"kid": localauth.LOCAL_KID},
    )
    assert client.get("/api/v1/suppliers", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_the_signing_key_survives_a_restart(client, tmp_path):
    """Otherwise every deploy silently signs everyone out."""
    from app.core import localauth

    first = _token(client)
    localauth.reset_cache()  # simulate a fresh process
    h = {"Authorization": f"Bearer {first}"}
    assert client.get("/api/v1/suppliers", headers=h).status_code == 200


def test_local_sign_in_can_be_turned_off(client, monkeypatch):
    """A deployment that has moved to a real IdP must not be walked past here."""
    from app.core.config import get_settings

    monkeypatch.setenv("AUTH_MODE", "oidc")
    get_settings.cache_clear()
    try:
        r = client.post("/api/v1/auth/session")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "LOCAL_AUTH_DISABLED"
    finally:
        get_settings.cache_clear()


def test_there_is_no_disable_auth_bypass(client, monkeypatch):
    """`DISABLE_AUTH=1` used to return a full-Admin actor with no token at all.

    It sat in `core/security.py` under a docstring stating that no such branch
    existed, and one environment variable turned the whole product into an open
    admin console. Setting it must now change nothing.
    """
    monkeypatch.setenv("DISABLE_AUTH", "1")
    assert client.get("/api/v1/suppliers").status_code == 401
    assert client.get("/api/v1/suppliers", headers={"Authorization": "Bearer anything"}).status_code == 401

    # Behaviour is the real assertion; this one stops the branch being
    # reintroduced somewhere the two requests above would not reach.
    import app.core.security as security

    with open(security.__file__, encoding="utf-8") as f:
        text = f.read()
    assert 'getenv("DISABLE_AUTH")' not in text
    assert 'environ["DISABLE_AUTH"]' not in text
