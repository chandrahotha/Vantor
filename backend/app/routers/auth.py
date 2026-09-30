"""Session routes for local, passwordless sign-in.

`POST /auth/session` is the whole of it: it mints a signed, expiring token for
the configured local operator. There is no password because there is no user
directory — see `core/localauth` for why that trade was made and what it costs.

`GET /auth/me` answers from the token the caller already holds, so the web app
can restore a session after a reload without re-issuing one, and so an operator
can check what a token actually grants without decoding it by hand.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core import localauth
from ..core.config import get_settings
from ..core.errors import envelope
from ..core.security import Actor, get_actor

router = APIRouter(tags=["auth"])


@router.post("/auth/session")
def create_session(request: Request) -> dict:
    """Start a local session.

    Deliberately unauthenticated — that is what "passwordless" means here. The
    route is refused outright when `AUTH_MODE` does not include `local`, so a
    deployment that has moved to a real identity provider cannot be walked past
    by calling this endpoint; it answers 404, not 401, because in that
    configuration the route genuinely does not exist as a way in.
    """
    if not localauth.enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "LOCAL_AUTH_DISABLED",
                "message": "This deployment authenticates against an identity provider. Sign in through it.",
            },
        )
    token, expires_in, profile = localauth.issue_session()
    return envelope(
        {"token": token, "tokenType": "Bearer", "expiresIn": expires_in, "user": profile},
        None,
        getattr(request.state, "request_id", ""),
    )


@router.get("/auth/me")
def whoami(request: Request, actor: Actor = Depends(get_actor)) -> dict:
    """Who the presented token says you are, and what it lets you do."""
    settings = get_settings()
    return envelope(
        {
            "sub": actor.sub,
            "tenant": actor.tenant_id,
            "email": actor.email,
            "name": actor.token_claims.get("name") or settings.local_user_name,
            "roles": list(actor.roles),
            # `local` for a passwordless session, absent for a federated one.
            "authSource": actor.token_claims.get("vantor_auth", "oidc"),
        },
        None,
        getattr(request.state, "request_id", ""),
    )


@router.get("/auth/config")
def auth_config(request: Request) -> dict:
    """What sign-in methods this deployment offers.

    The web app reads this before it renders the sign-in screen, so the button
    it shows matches what the server will actually accept. Hardcoding that in
    the client is how the old build ended up offering a Keycloak redirect in a
    deployment with no Keycloak.
    """
    settings = get_settings()
    return envelope(
        {
            "local": localauth.enabled(),
            "oidc": settings.auth_mode.strip().lower() in {"oidc", "both"},
            "productName": "VANTOR",
        },
        None,
        getattr(request.state, "request_id", ""),
    )
