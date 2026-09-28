"""Configuration defaults that are wrong in a way no endpoint test can see.

A default only earns its keep when it is correct for the case it covers. The
two below are checked against the files that state the same fact, because when
they disagreed the symptom was not a crash — it was `401 Invalid token` on
every authenticated request while `/health`, which touches no dependency, stayed
green, and the developer lost an afternoon to it.
"""
import re
from pathlib import Path

import pytest

from app.core.config import Settings

REPO = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO / ".env.example"


def env_example_value(name: str) -> str:
    """Read one `KEY=value` out of .env.example, ignoring comments."""
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()
    raise AssertionError(f"{name} is not set in {ENV_EXAMPLE}")


@pytest.fixture(autouse=True)
def _no_local_env(monkeypatch):
    """A developer's own .env must not decide what the defaults are."""
    for name in ("OIDC_ISSUER", "JWT_AUDIENCE", "DATABASE_URL", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})
    Settings.model_config["env_file"] = None
    yield
    Settings.model_config["env_file"] = ".env"


def test_default_oidc_issuer_matches_env_example():
    """The default must equal the `iss` Keycloak will actually mint.

    `jwt.decode(issuer=...)` compares this string exactly, so `127.0.0.1` and
    `localhost` are not interchangeable even though they are the same server.
    The realm's issuer is derived from KC_HOSTNAME, which compose pins to
    `http://localhost:8080`, so `localhost` is what ends up in the token.
    """
    expected = env_example_value("OIDC_ISSUER")
    assert Settings().oidc_issuer == expected, (
        "the default OIDC_ISSUER does not match .env.example; every real token "
        f"will fail verification with 401 Invalid token. "
        f"default={Settings().oidc_issuer!r} example={expected!r}")


def test_default_oidc_issuer_is_host_reachable():
    """The default must resolve on a developer machine, not only in Compose.

    It used to default to the `keycloak` service name, which is resolvable only
    inside the Compose network. A native `uvicorn` then answered 503 on every
    authenticated request because it could not fetch the JWKS.
    """
    issuer = Settings().oidc_issuer
    assert "keycloak:" not in issuer, (
        f"the default issuer points at the Compose service name: {issuer!r}")


def test_default_audience_matches_env_example_and_the_web_client():
    """The audience must be the client the web app actually uses.

    A token minted for `vantor-web` is not a token for anything else, and a
    mismatch is a 403 the developer reads as an RBAC problem.
    """
    expected = env_example_value("NEXT_PUBLIC_KEYCLOAK_CLIENT")
    assert Settings().jwt_audience == expected
    assert re.search(
        r"^NEXT_PUBLIC_KEYCLOAK_CLIENT=" + re.escape(expected) + r"$",
        ENV_EXAMPLE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )


def test_the_three_keycloak_hosts_agree():
    """backend default, .env.example and the Next client must name one realm.

    These are three files stating the same fact. They are allowed to disagree
    with docker-compose, which is in a different network and says so, but not
    with each other.
    """
    kc_url = env_example_value("NEXT_PUBLIC_KEYCLOAK_URL")
    realm = env_example_value("NEXT_PUBLIC_KEYCLOAK_REALM")
    assert Settings().oidc_issuer == f"{kc_url}/realms/{realm}"
