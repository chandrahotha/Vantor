"""Configuration defaults that are wrong in a way no endpoint test can see.

A default only earns its keep when it is correct for the case it covers. The
two below are checked against the files that state the same fact, because when
they disagreed the symptom was not a crash — it was `401 Invalid token` on
every authenticated request while `/health`, which touches no dependency, stayed
green, and the developer lost an afternoon to it.
"""
import re
import warnings
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


class TestRequireProdSecrets:
    """`require_prod_secrets` used to be `"" in val`, which is `True` for every
    string — the empty string is a substring of everything — so it refused to
    start in production no matter what was configured. It also demanded
    `JWT_SECRET`, `REFRESH_TOKEN_SECRET`, `ENCRYPTION_KEY` and
    `KEYCLOAK_CLIENT_SECRET`, none of which any code in this app reads, which
    meant a correctly configured deployment could never pass it either way.
    This is what makes the single-container image (`APP_ENV=production`,
    `AUTH_MODE=local`, SQLite, no S3) boot at all.
    """

    def test_single_container_profile_starts_clean(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "local")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        for name in ("OIDC_ISSUER", "JWT_AUDIENCE", "POSTGRES_PASSWORD",
                     "S3_ENDPOINT", "S3_BUCKET", "S3_SECRET_KEY"):
            monkeypatch.delenv(name, raising=False)
        Settings(_env_file=None).require_prod_secrets()  # must not raise

    def test_oidc_mode_without_issuer_is_refused(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "oidc")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        monkeypatch.delenv("OIDC_ISSUER", raising=False)
        with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
            Settings(_env_file=None).require_prod_secrets()

    def test_managed_postgres_url_needs_no_separate_password_var(self, monkeypatch):
        """A Postgres deployment described only by `DATABASE_URL` must boot.

        This test replaced `test_postgres_backend_without_password_is_refused`,
        which asserted the opposite. That assertion contradicted the principle
        this class exists to hold — "do not demand variables no code reads" —
        because `POSTGRES_PASSWORD` is read by docker-compose.yml's `migrate` and
        keycloak-db services and by *nothing* in this process: the password
        SQLAlchemy actually uses is inside the URL. So a managed-Postgres
        operator who supplied one correct `DATABASE_URL` was refused a start for
        missing a variable that could not change any behaviour. The gate got
        narrower and correct, not weaker: the next test keeps the URL itself
        under the placeholder check.
        """
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "oidc")
        monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com/realms/vantor")
        monkeypatch.setenv("JWT_AUDIENCE", "vantor-web")
        monkeypatch.setenv("DATABASE_URL", "postgresql://vantor:real-secret@db.example.com:5432/vantor")
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        Settings(_env_file=None).require_prod_secrets()  # must not raise

    def test_placeholder_postgres_url_is_still_refused(self, monkeypatch):
        """The credential still has to be a real one, wherever it lives."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "oidc")
        monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com/realms/vantor")
        monkeypatch.setenv("JWT_AUDIENCE", "vantor-web")
        monkeypatch.setenv("DATABASE_URL", "postgresql://vantor:change-me@db.example.com:5432/vantor")
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            Settings(_env_file=None).require_prod_secrets()

    def test_passwordless_local_auth_warns_in_production_but_starts(self, monkeypatch):
        """`AUTH_MODE=local` in production is loud, not fatal.

        It is the documented single-container identity path — `POST /auth/session`
        hands a Super Admin token to anyone who can reach the port — so the
        supported answer is to say it on every boot and report it in `/ready`,
        not to refuse a boot that the README's headline quickstart depends on.
        Silence was the defect: a production deployment could be running with no
        credential boundary and leave nothing in its own logs to indicate it.
        """
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "local")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        settings = Settings(_env_file=None)
        assert settings.passwordless_local_auth is True
        with pytest.warns(RuntimeWarning, match="any caller who can reach the API"):
            settings.require_prod_secrets()

    def test_oidc_mode_does_not_warn_about_local_auth(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "oidc")
        monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com/realms/vantor")
        monkeypatch.setenv("JWT_AUDIENCE", "vantor-web")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        settings = Settings(_env_file=None)
        assert settings.passwordless_local_auth is False
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            settings.require_prod_secrets()  # must not warn, must not raise

    def test_s3_configured_without_secret_key_is_refused(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "local")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        monkeypatch.setenv("S3_ENDPOINT", "https://s3.example.com")
        monkeypatch.setenv("S3_BUCKET", "vantor-docs")
        monkeypatch.delenv("S3_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="S3_SECRET_KEY"):
            Settings(_env_file=None).require_prod_secrets()

    def test_placeholder_value_is_still_refused(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "oidc")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////data/vantor.db")
        monkeypatch.setenv("OIDC_ISSUER", "http://localhost:8080/realms/vantor")
        monkeypatch.setenv("JWT_AUDIENCE", "change-me")
        with pytest.raises(RuntimeError, match="JWT_AUDIENCE"):
            Settings(_env_file=None).require_prod_secrets()

    def test_development_mode_is_never_checked(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        for name in ("DATABASE_URL", "OIDC_ISSUER", "JWT_AUDIENCE", "POSTGRES_PASSWORD"):
            monkeypatch.delenv(name, raising=False)
        Settings(_env_file=None).require_prod_secrets()  # must not raise
