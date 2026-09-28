"""Keycloak OIDC authentication — real JWKS verification, fail-closed.

Pattern ported from ContractGuard/CostPilot/ProcurementOS convergence:
- RS256 JWTs verified against Keycloak JWKS (cached, refreshed on kid miss).
- Validates iss, aud, exp. No dev bypass, no hardcoded tokens, no anon-auth flag.
- In unit tests callers inject a test JWKS via `override_jwks()` — still real crypto.

Claims mapping:
- sub -> user id, tenant_id (or org_id) -> tenant, realm_access.roles + resource_access -> roles.
- Missing tenant claim => 403 (never guess a tenant).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from .config import get_settings

_bearer = HTTPBearer(auto_error=False)
_jwks_cache: dict = {"keys": {}, "fetched_at": 0.0}
_jwks_override: dict | None = None
_JWKS_TTL_S = 300.0


@dataclass(frozen=True)
class Actor:
    sub: str
    tenant_id: str
    email: str = ""
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = field(default_factory=tuple)
    token_claims: dict = field(default_factory=dict, compare=False)


def override_jwks(keys: dict | None) -> None:
    """Test hook only: inject {kid: public_key_pem_or_jwk} for real verification."""
    global _jwks_override
    _jwks_override = keys


def _fetch_jwks() -> dict:
    """Return the provider's signing keys, from cache when warm.

    VNT-029. This performs a blocking `httpx.get` and was reached from `async
    def` request paths with no offload, so on a cache miss the event loop sat
    through a 5-second network timeout — taking every concurrent request with it.
    Callers on the async path must use `fetch_jwks_async`; this sync form remains
    for startup, scripts and synchronous callers.
    """
    if _jwks_override is not None:
        return _jwks_override
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < _JWKS_TTL_S:
        return _jwks_cache["keys"]
    settings = get_settings()
    try:
        resp = httpx.get(settings.jwks_url, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # fail-closed: auth unavailable => 503, never anonymous
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Identity provider unavailable") from exc
    keys = {k["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(k) for k in data.get("keys", []) if k.get("kid")}
    _jwks_cache.update(keys=keys, fetched_at=now)
    return keys


async def fetch_jwks_async() -> dict:
    """`fetch_jwks` without blocking the event loop.

    The cache check and the fetch are both fast paths we would rather not pay a
    thread hop for, so the TTL check happens inline and only a cold fetch is
    handed to a worker thread.
    """
    if _jwks_override is not None:
        return _jwks_override
    if _jwks_cache["keys"] and (time.time() - _jwks_cache["fetched_at"]) < _JWKS_TTL_S:
        return _jwks_cache["keys"]
    return await run_in_threadpool(_fetch_jwks)


async def verify_token_async(token: str) -> Actor:
    """`verify_token`, off the event loop only where it can actually block.

    VNT-029. The blocking part is the JWKS *fetch* — a network call with a 5s
    timeout, reached on a cache miss and on a key rotation, straight from an
    `async def` on every request. RSA verification is CPU-bound but short
    (~sub-millisecond for RSA-2048), and offloading it would cost a thread hop on
    every single request in exchange for nothing, which is why the whole suite
    roughly doubled in wall time the first time this was written that way.

    So: warm cache and test override are handled inline, and the cold path is
    handed to a worker thread.
    """
    if _jwks_override is not None or (
        _jwks_cache["keys"] and (time.time() - _jwks_cache["fetched_at"]) < _JWKS_TTL_S
    ):
        return verify_token(token)
    return await run_in_threadpool(verify_token, token)


def _public_key_for(kid: str):  # type: ignore[no-untyped-def]
    keys = _fetch_jwks()
    key = keys.get(kid)
    if key is None and _jwks_override is None:
        # Refresh once on kid miss (rotation), then give up.
        _jwks_cache["fetched_at"] = 0.0
        key = _fetch_jwks().get(kid)
    if key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token key")
    return key


def verify_token(token: str) -> Actor:
    """Verify one bearer token. Fail-closed in every environment.

    There is no non-production branch here on purpose, and its absence is
    enforced by `tests/test_auth.py::test_forged_tokens_are_401_in_test_env`
    and `::test_development_env_also_fails_closed`. Three separate
    `if not settings.is_prod` escapes were added here to keep the app usable
    when the IdP was unreachable. They were not a development convenience —
    they minted a full Admin actor for `Bearer vantor-<anything>`, for any
    unparseable token, and for any unknown `kid`, in dev, staging *and* test:

        GET /api/v1/me  Authorization: Bearer vantor-attacker
        200  {"tenantId": "vantor-corp",
              "roles": ["Buyer", "Procurement Manager", "Admin", "Approver"]}

    The three causes of that pressure are fixed instead: `Settings.oidc_issuer`
    now defaults to a host-reachable address rather than the Compose service
    name, the realm imports within Keycloak's column limits, and the API
    clients carry the `aud` claim the backend requires. A developer who needs a
    token runs Keycloak; an attacker who can guess a prefix gets a 401.
    """
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token") from exc
    if header.get("alg") != "RS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported token algorithm")
    key = _public_key_for(header.get("kid", ""))
    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    tenant_id = claims.get("tenant_id") or claims.get("org_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token carries no tenant")
    roles: list[str] = []
    realm = (claims.get("realm_access") or {}).get("roles", [])
    roles.extend(realm)
    for res in (claims.get("resource_access") or {}).values():
        roles.extend(res.get("roles", []))
    return Actor(
        sub=str(claims["sub"]),
        tenant_id=str(tenant_id),
        email=str(claims.get("email", "")),
        roles=tuple(sorted(set(roles))),
        scopes=tuple((claims.get("scope", "") or "").split()),
        token_claims=claims,
    )


async def get_actor(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Actor:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    # VNT-029: verification is CPU-bound (RSA) and may need the network (JWKS),
    # and this is an `async def` on every authenticated request.
    actor = await verify_token_async(creds.credentials)
    request.state.actor = actor
    request.state.tenant_id = actor.tenant_id
    return actor


def require_roles(*allowed: str):  # type: ignore[no-untyped-def]
    async def _check(actor: Actor = Depends(get_actor)) -> Actor:
        if not allowed:
            return actor
        if not set(actor.roles) & set(allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return actor

    return _check
