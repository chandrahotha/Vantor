"""Local, passwordless sign-in — the API as its own identity provider.

Why this exists
---------------
Every route is behind `get_actor`, and `get_actor` only accepted a Keycloak
token. So the product could not be opened at all without a second service
running: with Keycloak down, "Sign in" navigated the browser to
`localhost:8080` and the user got `ERR_CONNECTION_REFUSED`. For a product meant
to be deployable free, in one container, an identity server is a dependency the
deployment cannot carry.

What it does
------------
The API holds an RSA keypair, generated on first use and persisted, and mints
its own RS256 tokens with the same claim shape Keycloak produces:

    {iss, aud, sub, tenant_id, email, realm_access: {roles}, iat, exp}

`security.verify_token` is unchanged. It resolves the `kid`, checks the
signature, the issuer, the audience and the expiry, and reads the tenant and
roles out of the claims exactly as before. Tenancy, RLS, role checks,
segregation of duties and the audit actor all keep working, because none of
them ever knew where the token came from.

What it deliberately does not do
--------------------------------
It does not ask for a password. `POST /auth/session` hands a session to anyone
who can reach it. That is the explicit trade for a single-container, no-IdP
deployment: **anyone who can reach the API is the operator.** Do not expose
such a deployment to a network you do not control. `AUTH_MODE=oidc` restores
the Keycloak-only behaviour, and both modes can run together — a local token
and a Keycloak token are both just RS256 tokens with a resolvable `kid`.

The token is still signed, still expires, and still carries a tenant. That is
what keeps every downstream control honest, and it is what makes adding real
credentials later a change to *this* file only.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .config import get_settings

#: Stable key id for the locally-issued key. It never collides with a Keycloak
#: `kid`, which is a base64url digest, so `security._public_key_for` can check
#: the local key first and fall through to JWKS without ambiguity.
LOCAL_KID = "vantor-local-v1"

_lock = threading.Lock()
_cache: dict[str, object] = {}


def _key_file() -> Path:
    return Path(get_settings().local_key_path)


def _load_or_create() -> rsa.RSAPrivateKey:
    """The signing key, generated once and reused.

    Persisted rather than held in memory so that restarting the API does not
    silently invalidate every open session — which would show up to a user as
    being logged out at random, with no error to explain it.
    """
    path = _key_file()
    if path.exists():
        try:
            loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if isinstance(loaded, rsa.RSAPrivateKey):
                return loaded
        except Exception:
            # A corrupt or truncated key file is replaced rather than crashing
            # the API on boot. Existing sessions die with it, which is correct:
            # the server cannot vouch for a token it can no longer verify.
            pass
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pem)
        # Owner-only where the platform honours it. Best-effort: a read-only
        # filesystem is a supported deployment and must not stop the API.
        try:
            path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
    except OSError:
        # Ephemeral key. Sessions then last until the next restart, which is
        # degraded but working — better than refusing to serve.
        pass
    return key


def signing_key() -> rsa.RSAPrivateKey:
    key = _cache.get("private")
    if key is None:
        with _lock:
            key = _cache.get("private")
            if key is None:
                key = _load_or_create()
                _cache["private"] = key
    return key  # type: ignore[return-value]


def public_keys() -> dict:
    """`{kid: public_key}`, in the shape `security._public_key_for` expects."""
    return {LOCAL_KID: signing_key().public_key()}


def reset_cache() -> None:
    """Drop the in-process key so the next call re-reads the file. Tests use it."""
    with _lock:
        _cache.clear()


def roles() -> tuple[str, ...]:
    raw = get_settings().local_roles
    return tuple(sorted({r.strip() for r in raw.split(",") if r.strip()}))


def issue_session() -> tuple[str, int, dict]:
    """Mint one local session token.

    Returns `(token, expires_in_seconds, profile)`. The profile is what the web
    app shows in the sidebar; it is derived from the same claims that go into
    the token, so the two cannot disagree.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl = timedelta(hours=settings.local_session_hours)
    claims = {
        "iss": settings.oidc_issuer,
        "aud": settings.jwt_audience,
        "sub": "local-operator",
        "tenant_id": settings.local_tenant,
        "email": settings.local_user_email,
        "name": settings.local_user_name,
        "realm_access": {"roles": list(roles())},
        "iat": now,
        "exp": now + ttl,
        # Marks where the session came from. The audit trail records the actor,
        # and an operator reading it later should be able to tell a local
        # passwordless session from a federated identity.
        "vantor_auth": "local",
    }
    pem = signing_key().private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = jwt.encode(claims, pem, algorithm="RS256", headers={"kid": LOCAL_KID})
    profile = {
        "name": settings.local_user_name,
        "email": settings.local_user_email,
        "tenant": settings.local_tenant,
        "roles": list(roles()),
    }
    return token, int(ttl.total_seconds()), profile


def enabled() -> bool:
    return get_settings().auth_mode.strip().lower() in {"local", "both"}
