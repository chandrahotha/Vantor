"""Identity read API — current actor context for premium UI shell.

- GET /api/v1/me: verified JWT claims (sub, tenant, email, roles). No DB hit,
  so the web shell + dashboards can render user/tenant context even when the
  database is mid-migration. Authorization-gated, never anonymous.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..core.errors import envelope
from ..core.security import Actor, get_actor

router = APIRouter(tags=["identity"])


@router.get("/me")
def me(request: Request, actor: Actor = Depends(get_actor)) -> dict:
    rid = getattr(request.state, "request_id", "")
    return envelope(
        {
            "sub": actor.sub,
            "tenantId": actor.tenant_id,
            "email": actor.email,
            "roles": list(actor.roles),
            "scopes": list(actor.scopes),
        },
        None,
        rid,
    )
