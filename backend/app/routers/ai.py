"""AI API — gateway completions + typed tools, evidence-first, HITL by default.

- POST /ai/complete {prompt, provider?}: runs the gateway; failures surface the
  provider name (never silent fallback); every success requires human review.
- POST /ai/tools/{name} {args}: executes a typed, tenant-scoped tool with role
  check; logged as AI_TOOL_EXECUTED with evidence refs.
- GET /ai/providers: configured provider + available list (no keys exposed).
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.errors import envelope
from ..core.security import Actor, get_actor
from ..core.tenant import get_db
from ..services.ai_gateway import AIGatewayError, complete, providers_configured
from ..services.ai_tools import REGISTRY, ToolError, check_tool_access, check_tool_args
from ..services.audit import record_event

router = APIRouter(tags=["ai"])


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


class CompleteIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=8000)
    provider: str = ""
    system: str = ""


class NegoIn(BaseModel):
    list_price_minor: int = Field(gt=0)
    walk_away_minor: int = Field(gt=0)
    buyer_offers_minor: list[int] = Field(min_length=1, max_length=10)
    max_rounds: int = Field(default=5, ge=1, le=10)
    concession_bp: int = Field(default=1500, ge=1, le=10_000)


@router.post("/ai/negotiate")
def negotiate(payload: NegoIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """10 Negotiation Simulator: deterministic rehearsal. Labeled simulation —
    never touches live RFQs, quotes, or orders."""
    from ..services.negosim import NegoError, simulate

    try:
        out = simulate(list_price_minor=payload.list_price_minor, walk_away_minor=payload.walk_away_minor,
                       buyer_offers_minor=payload.buyer_offers_minor, max_rounds=payload.max_rounds,
                       concession_bp=payload.concession_bp)
    except NegoError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_TOOL_EXECUTED", resource="ai_tool",
                 resource_id="negotiate", after={"result": out["result"], "score": out["score"]}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"simulation": True, **out, "requiresHumanReview": True}, None, getattr(request.state, "request_id", ""))


@router.get("/ai/providers")
def providers(request: Request, actor: Actor = Depends(get_actor)) -> dict:
    from ..core.config import get_settings

    return envelope({"active": get_settings().ai_provider, "available": providers_configured()}, None, getattr(request.state, "request_id", ""))


@router.post("/ai/complete")
def run_complete(payload: CompleteIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    try:
        result = complete(prompt=payload.prompt, system=payload.system, provider=payload.provider)
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail={"code": "AI_PROVIDER_FAILED", "message": exc.message, "details": {"provider": exc.provider}}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_COMPLETED", resource="ai",
                 resource_id="complete", after={"provider": result["provider"]}, source="api", created_by=actor.sub)
    db.commit()
    return envelope(result, None, getattr(request.state, "request_id", ""))


@router.post("/ai/tools/{name}")
def run_tool(name: str, args: dict, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    try:
        check_tool_access(actor.roles, name)
        check_tool_args(name, args or {})
    except ToolError as exc:
        raise HTTPException(status_code=403 if exc.code == "TOOL_FORBIDDEN" else 404 if exc.code == "TOOL_UNKNOWN" else 422,
                            detail={"code": exc.code, "message": exc.message}) from exc
    try:
        out = REGISTRY[name](db, actor.tenant_id, **{k: v for k, v in (args or {}).items() if k in ("q", "limit", "supplier_id", "rfq_id", "status")})
    except ToolError as exc:
        raise HTTPException(status_code=404 if exc.code == "NOT_FOUND" else 422, detail={"code": exc.code, "message": exc.message}) from exc
    except TypeError as exc:
        raise HTTPException(status_code=422, detail={"code": "TOOL_ARGS_INVALID", "message": f"Bad args for {name}"}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_TOOL_EXECUTED", resource="ai_tool",
                 resource_id=name, after={"args": args}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"tool": name, "result": out, "requiresHumanReview": True}, None, getattr(request.state, "request_id", ""))
