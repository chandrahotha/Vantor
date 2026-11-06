"""`GET /auth/config` — the endpoint the browser trusts to say where to sign in.

This had no test at all, which was tolerable while nothing called it. It is not
tolerable now: the web app reads this response to decide which authorization
endpoint to redirect a user to and which token endpoint to post an authorization
code to. A wrong value here is not a cosmetic bug — it is the login sending a
credential somewhere other than the operator's identity provider.

The endpoint is also the only place the OIDC parameters exist at runtime. They
used to be `NEXT_PUBLIC_KEYCLOAK_URL/REALM/CLIENT` build-time constants that no
code read, pointing at a realm the app had stopped talking to, and that could not
be changed without rebuilding the image.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    def build(auth_mode: str, issuer: str = "https://idp.test/realms/vantor"):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("DATABASE_URL", "sqlite://")
        monkeypatch.setenv("OIDC_ISSUER", issuer)
        monkeypatch.setenv("JWT_AUDIENCE", "vantor-web")
        monkeypatch.setenv("AUTH_MODE", auth_mode)
        get_settings.cache_clear()
        return TestClient(app)

    yield build
    get_settings.cache_clear()


def test_local_mode_offers_local_only(client):
    body = client("local").get("/api/v1/auth/config").json()["data"]
    assert body["local"] is True
    assert body["oidc"] is False
    # Nothing about an IdP is advertised when there is none: the client keys on
    # this being absent to decide not to offer a redirect at all.
    assert body["oidcProvider"] is None


def test_oidc_mode_publishes_the_endpoints_the_browser_needs(client):
    body = client("oidc").get("/api/v1/auth/config").json()["data"]
    assert body["local"] is False
    assert body["oidc"] is True
    provider = body["oidcProvider"]
    assert provider["clientId"] == "vantor-web"
    assert provider["issuer"] == "https://idp.test/realms/vantor"
    assert provider["authorizationEndpoint"] == (
        "https://idp.test/realms/vantor/protocol/openid-connect/auth")
    assert provider["tokenEndpoint"] == (
        "https://idp.test/realms/vantor/protocol/openid-connect/token")
    # Derived from the issuer the API itself verifies tokens against — one
    # source of truth, so the browser cannot be pointed at a different realm
    # than the one whose keys the backend accepts.
    assert provider["issuer"] == get_settings().oidc_issuer.rstrip("/")


def test_a_trailing_slash_on_the_issuer_does_not_double_up(client):
    body = client("oidc", issuer="https://idp.test/realms/vantor/").get(
        "/api/v1/auth/config").json()["data"]
    endpoint = body["oidcProvider"]["tokenEndpoint"]
    assert "//protocol" not in endpoint, endpoint
    assert endpoint == "https://idp.test/realms/vantor/protocol/openid-connect/token"


def test_both_mode_offers_both_paths(client):
    body = client("both").get("/api/v1/auth/config").json()["data"]
    assert body["local"] is True and body["oidc"] is True


def test_the_config_carries_no_secret(client):
    """Public by necessity, so it must leak nothing.

    The route is unauthenticated because the sign-in screen calls it before
    there is a session. That is fine while it only names public parameters; a
    client secret in here would be a credential readable by anyone who can reach
    the port.
    """
    body = client("oidc").get("/api/v1/auth/config").json()
    blob = str(body).lower()
    for forbidden in ("secret", "password", "token\"", "private_key"):
        assert forbidden not in blob, f"{forbidden!r} appeared in /auth/config"


def test_the_endpoint_needs_no_session(client):
    response = client("oidc").get("/api/v1/auth/config")
    assert response.status_code == 200, response.text
