"""Session routes for local, passwordless sign-in.

`POST /auth/session` is the whole of it: it mints a signed, expiring token for
the configured local operator. There is no password because there is no user
directory — see `core/localauth` for why that trade was made and what it costs.

`GET /auth/me` answers from the token the caller already holds, so the web app
can restore a session after a reload without re-issuing one, and so an operator
can check what a token actually grants without decoding it by hand.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core import localauth
from ..core.config import get_settings
from ..core.errors import envelope
from ..core.security import Actor, get_actor

router = APIRouter(tags=["auth"])


class SessionIn(BaseModel):
    #: Which named local identity to sign in as — see `core.localauth.PERSONAS`.
    #: Unset or unrecognised falls back to the default operator persona, so
    #: existing callers that post no body keep today's exact behaviour.
    persona: str = Field(default=localauth.DEFAULT_PERSONA, max_length=40)


@router.post("/auth/session")
def create_session(request: Request, payload: SessionIn | None = Body(default=None)) -> dict:
    """Start a local session.

    Deliberately unauthenticated — that is what "passwordless" means here. The
    route is refused outright when `AUTH_MODE` does not include `local`, so a
    deployment that has moved to a real identity provider cannot be walked past
    by calling this endpoint; it answers 404, not 401, because in that
    configuration the route genuinely does not exist as a way in.

    `persona` picks which named local identity the token is issued for (see
    `GET /auth/personas`). It does not change what the token permits — there is
    one operator and every persona holds the full configured role set — it
    changes `sub`, so a requester and an approver can be recorded as distinct
    identities and segregation-of-duties checks can actually be satisfied by
    the one physical operator switching hats.
    """
    if not localauth.enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "LOCAL_AUTH_DISABLED",
                "message": "This deployment authenticates against an identity provider. Sign in through it.",
            },
        )
    token, expires_in, profile = localauth.issue_session(payload.persona if payload else localauth.DEFAULT_PERSONA)
    return envelope(
        {"token": token, "tokenType": "Bearer", "expiresIn": expires_in, "user": profile},
        None,
        getattr(request.state, "request_id", ""),
    )


@router.get("/auth/personas")
def list_personas(request: Request) -> dict:
    """Named local identities `POST /auth/session` will accept.

    404s under `AUTH_MODE=oidc` for the same reason `/auth/session` does: in
    that configuration this is not a way to sign in, so it does not exist.
    """
    if not localauth.enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "LOCAL_AUTH_DISABLED",
                "message": "This deployment authenticates against an identity provider.",
            },
        )
    personas = [{"key": k, "label": v} for k, v in localauth.PERSONAS.items()]
    return envelope({"personas": personas, "default": localauth.DEFAULT_PERSONA},
                    None, getattr(request.state, "request_id", ""))


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
            "persona": actor.token_claims.get("vantor_local_persona", ""),
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
