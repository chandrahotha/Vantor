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
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
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
        allowed = {"q", "limit", "supplier_id", "rfq_id", "status", "action", "resource", "resource_id", "reason"}
        kwargs = {k: v for k, v in (args or {}).items() if k in allowed}
        if name == "request_approval":
            kwargs["requested_by"] = actor.sub
        out = REGISTRY[name](db, actor.tenant_id, **kwargs)
    except ToolError as exc:
        raise HTTPException(status_code=404 if exc.code == "NOT_FOUND" else 422, detail={"code": exc.code, "message": exc.message}) from exc
    except TypeError as exc:
        raise HTTPException(status_code=422, detail={"code": "TOOL_ARGS_INVALID", "message": f"Bad args for {name}"}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_TOOL_EXECUTED", resource="ai_tool",
                 resource_id=name, after={"args": args}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"tool": name, "result": out, "requiresHumanReview": True}, None, getattr(request.state, "request_id", ""))


class DecideIn(BaseModel):
    approve: bool = False
    reason: str = ""


@router.post("/ai/approvals/{approval_id}/decide", status_code=200)
def decide_approval(approval_id: str, payload: DecideIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    """HITL decision on an AI-filed approval. Approving here records consent;
    the caller then performs the action through the normal API (nothing auto-executes)."""
    from ..models.purchase import Approval
    from ..services.purchase import check_sod

    row = db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.id == approval_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if not row.resource.startswith("ai:"):
        raise HTTPException(status_code=422, detail="Not an AI-filed approval")
    if row.status != "requested":
        raise HTTPException(status_code=422, detail="Already decided")
    try:
        check_sod(row.created_by, actor.sub)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Requester cannot decide their own filing") from exc
    if not set(actor.roles or ()) & {"Super Admin", "Organization Admin", "Procurement Admin", "Procurement Manager", "Approver"}:
        raise HTTPException(status_code=403, detail="Approver role required")
    row.status, row.decided_by, row.reason, row.updated_by = ("approved" if payload.approve else "rejected",
                                                              actor.sub, payload.reason.strip(), actor.sub)
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_APPROVAL_DECIDED", resource="ai_tool",
                 resource_id=approval_id, after={"approved": payload.approve}, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": approval_id, "status": row.status}, None, getattr(request.state, "request_id", ""))


@router.post("/ai/stream")
def run_stream(payload: CompleteIn, request: Request, actor: Actor = Depends(get_actor)) -> Response:
    """SSE completions: `data: {delta}` frames + terminal `data: [EVIDENCE] {...}`.

    Honest about what it is: frames are cut from the *completed* provider
    response, so time-to-first-byte equals the blocking call. Provider-side
    token streaming is not wired (see `services/ai_gateway.py`).
    Disabled/unconfigured providers emit an honest error event, never fake tokens.
    """
    import json as _json

    from fastapi.responses import StreamingResponse as _SS

    from ..services.ai_gateway import complete as _complete

    rid = getattr(request.state, "request_id", "")
    tenant, sub = actor.tenant_id, actor.sub

    def _events():  # type: ignore[no-untyped-def]
        from ..core.tenant import pinned_session
        from ..services.audit import record_event as _rec

        try:
            result = _complete(prompt=payload.prompt, system=payload.system, provider=payload.provider)
        except AIGatewayError as exc:
            yield f"data: {_json.dumps({'error': exc.message, 'provider': exc.provider})}\n\n"
            return
        text = result.get("answer", "")
        for i in range(0, max(len(text), 1), 120):
            yield f"data: {_json.dumps({'delta': text[i:i + 120], 'streamed': False})}\n\n"
        yield f"data: [EVIDENCE] {_json.dumps({'confidence': result.get('confidence'), 'provider': result.get('provider'), 'evidence': result.get('evidence', []), 'requires_human_review': True, 'requestId': rid})}\n\n"
        # Pinned session: an unpinned one is rejected by the audit_events RLS
        # policy on Postgres, which would silently drop every streamed audit.
        db = None
        try:
            db = pinned_session(tenant)
            _rec(db, tenant_id=tenant, actor=sub, action="AI_COMPLETED", resource="ai",
                 resource_id="stream", after={"provider": result.get("provider")}, source="api", created_by=sub)
            db.commit()
        except Exception:
            if db is not None:
                db.rollback()
        finally:
            if db is not None:
                db.close()

    return _SS(_events(), media_type="text/event-stream",
               headers={"X-Request-ID": rid, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
