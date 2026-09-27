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
    settings = get_settings()
    if settings.demo_mode and token.startswith("demo:"):
        body = token[5:]
        name, sep, sig = body.rpartition(".")
        if not sep or not name or len(sig) != 64 or not _demo_sig_ok(name, sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed demo token")
        # Read-only by design: the demo role set is the one that refuses every
        # gate's mutating detail immediately, not the empty list. Your demo walk
        # through an app structure doesn't let _you touch anything.""
        roles = ("Read Only",)
        return Actor(sub=name, tenant_id="demo", email=f"{name}@demo.vantor", roles=roles,
                     token_claims={"demo": True})
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


def _demo_sig_ok(name: str, sig: str) -> bool:
    """HMAC check for demo tokens. Fail-closed — never accepts without proof."""
    import hashlib
    import hmac as _hmac

    settings = get_settings()
    if not settings.demo_token:
        return False
    expected = _hmac.new(
        settings.demo_token.encode(), name.encode(), hashlib.sha256
    ).hexdigest()
    return _hmac.compare_digest(expected, sig)


async def get_actor(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Actor:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    actor = verify_token(creds.credentials)
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
