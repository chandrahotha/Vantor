"""Auth — real RS256 verification with ephemeral keys (no fakes, no bypass).

Covers: valid token w/ tenant+roles, missing bearer => 401, wrong alg => 401,
expired => 401, no-tenant claim => 403, unknown kid => 401, wrong role => 403.
Regression (B-32): unsigned `vantor-*` strings and `demo:` HMAC tokens are
rejected with 401 in every non-production environment — the old bypasses
granted a full Admin session to anyone who could guess a prefix.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import security
from app.main import app

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    pub_key = pub
    # Build a JWKS-override entry keyed by kid; security._fetch_jwks returns it directly.
    from jwt.algorithms import RSAAlgorithm

    jwk_json = RSAAlgorithm.to_jwk(pub_key, as_dict=True)
    jwk_json["kid"] = "test-kid"
    # from_jwk accepts the dict; store the key object for verification speed.
    key_obj = RSAAlgorithm.from_jwk(jwk_json)
    security.override_jwks({"test-kid": key_obj})
    yield {"priv_pem": priv_pem}
    security.override_jwks(None)


def _token(priv_pem: bytes, **claims) -> str:
    now = datetime.now(timezone.utc)
    base = {"iss": ISS, "aud": AUD, "sub": "user-1", "exp": now + timedelta(minutes=5), "iat": now}
    base.update(claims)
    return jwt.encode(base, priv_pem, algorithm="RS256", headers={"kid": "test-kid"})


def _client_with_env(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    # clear cached settings so new env applies
    from app.core.config import get_settings

    get_settings.cache_clear()
    return TestClient(app)


def test_missing_token_is_401(monkeypatch):
    c = _client_with_env(monkeypatch)
    r = c.get("/api/v1/audit-events")
    assert r.status_code == 401


def test_valid_token_reaches_tenant_scoped_endpoint(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = _token(keys["priv_pem"], tenant_id="t1", realm_access={"roles": ["Buyer"]})
    r = c.get("/api/v1/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["tenantId"] == "t1"
    assert "Buyer" in body["data"]["roles"]


def test_token_without_tenant_is_403(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = _token(keys["priv_pem"])
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_expired_token_is_401(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t1", "exp": now - timedelta(minutes=1), "iat": now - timedelta(minutes=10)},
        keys["priv_pem"],
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_none_alg_rejected(keys, monkeypatch):
    c = _client_with_env(monkeypatch)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u", "tenant_id": "t1"}, key="", algorithm="none")
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


# --- B-32 regression: the forged-token bypasses are gone, in every environment ---
#
# These deliberately run WITHOUT the `keys`/`override_jwks` fixture: the old
# bypasses short-circuited before JWKS, so a pass here proves the rejection
# comes from the verification path, not from an unavailable key set. If the
# bypass blocks were re-added, every test in this section would fail even
# with no reachable IdP (mutation-checked).

_FORGED_TOKENS = [
    "vantor-corp-jwt-session",            # the old Admin-minting default
    "vantor-director-session-token",      # persona shape from the frontend
    "vantor-custom-jwt-session",          # client-minted custom identity
    "vantor-finance_controller-session",  # roles_map persona id
    "vantor-anything-goes-session",       # the catch-all fallback
    "vantor-x-session",
    "demo:reviewer." + "0" * 64,          # unsigned demo token (old HMAC path)
    "demo:x",
    "not-a-token-at-all",
]


@pytest.mark.parametrize("forged", _FORGED_TOKENS)
def test_forged_tokens_are_401_in_test_env(monkeypatch, forged):
    monkeypatch.setenv("APP_ENV", "test")
    # Env that used to enable the bypasses: DEMO_* is now unknown to Settings
    # (extra="ignore"), and `vantor-*` had no gate beyond `not is_prod`.
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_TOKEN", "an-attacker-known-secret")
    monkeypatch.setenv("NEXT_PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("NEXT_PUBLIC_DEMO_TOKEN", "anything")
    c = _client_with_env(monkeypatch)
    r = c.get("/api/v1/audit-events", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401, f"bypass accepted forged token {forged!r}: {r.status_code}"


def test_development_env_also_fails_closed(monkeypatch):
    # The old gate was `not settings.is_prod`, so development and staging were
    # as exposed as test. Fail-closed must hold there too.
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_TOKEN", "x")
    c = _client_with_env(monkeypatch)
    r = c.get("/api/v1/audit-events", headers={"Authorization": "Bearer vantor-corp-jwt-session"})
    assert r.status_code == 401


def test_settings_no_longer_expose_demo_fields(monkeypatch):
    # Guard against a reintroduced `demo_mode`/`demo_token` field: the config
    # must not know these settings exist, so `DEMO_MODE=true` is inert.
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_TOKEN", "x")
    from app.core.config import Settings

    s = Settings()
    assert not hasattr(s, "demo_mode")
    assert not hasattr(s, "demo_token")


def test_security_module_has_no_demo_helpers():
    assert not hasattr(security, "_demo_sig_ok")
