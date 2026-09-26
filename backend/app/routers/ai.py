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
from ..services.ai_gateway import AIGatewayError, complete
from ..services.ai_tools import REGISTRY, ToolError, check_tool_access, check_tool_args
from ..services.audit import record_event
import json

router = APIRouter(tags=["ai"])

# Deliberately no blanket role gate on this surface. The copilot's honesty design
# is that a caller *without* permission for a tool still gets an answer, with the
# refusal admitted in `notes` rather than hidden behind a 403. A gate here would
# destroy that: `test_grounding_respects_role_gates` pins the behaviour, and it
# is the right behaviour. The real control is per-tool (`check_tool_access` in
# `run_tool` and `COPILOT_TOOL_ARG_KEYS` for copilot-invoked tools), and
# `request_approval` — the only mutating tool — is deliberately not copilot-
# reachable and requires an Approver-role decision through the HITL endpoint.
# Provider spend is bounded by the rate limiter, and every call is audited.


def db_for_actor(actor: Actor = Depends(get_actor)) -> Generator[Session, None, None]:
    yield from get_db(actor.tenant_id)


class CompleteIn(BaseModel):
    prompt: str = Field(min_length=2, max_length=8000)
    provider: str = ""
    model: str = Field(default="", max_length=200)
    # Per-request BYOK key, never stored server-side and excluded from audit.
    # `X-Vantor-Provider-Key` is preferred so the key never rides in the body.
    provider_key: str = Field(default="", max_length=500)
    system: str = Field(default="", max_length=8000)
    tools: list[ToolCallIn] | None = None


def _provider_key_of(request: Request, payload: CompleteIn) -> str:
    """Header wins over body: keeps the key out of any body-level capture."""
    return (request.headers.get("X-Vantor-Provider-Key", "") or payload.provider_key).strip()


def _check_provider(payload: CompleteIn) -> None:
    """Reject a provider this build does not know with 422, not a downstream 502.

    The list of known names travels with the error so a client can self-correct
    without reading the source.
    """
    from ..services.ai_gateway import PROVIDERS, _active_provider

    if _active_provider(payload.provider) not in PROVIDERS:
        raise HTTPException(status_code=422, detail={
            "code": "AI_PROVIDER_UNKNOWN",
            "message": f"unknown provider {payload.provider!r}",
            "details": {"known": sorted(PROVIDERS)},
        })


class ToolCallIn(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


# Read-only tools the copilot may invoke. request_approval stays OUT — the
# copilot can never execute it, it must go through the HITL endpoint.
COPILOT_TOOL_ARG_KEYS: dict[str, set[str]] = {
    "search_suppliers": {"q", "limit"},
    "get_supplier": {"supplier_id"},
    "compare_quotes": {"rfq_id"},
    "calculate_savings": set(),
    "get_purchase_orders": {"status", "limit"},
}


def _run_copilot_tools(calls: list[ToolCallIn] | None, actor: Actor, db: Session, rid: str) -> tuple[list[str], list[dict], list[str]]:
    """Run the tools the copilot asked for. Returns (context_blocks, evidence,
    notes). Notes are explicit in the answer so a failed tool is admitted,
    never hidden."""
    if not calls:
        return [], [], []
    blocks: list[str] = []
    evidence: list[dict] = []
    notes: list[str] = []
    for call in calls[:6]:
        name, args = call.name, call.args or {}
        try:
            if name not in COPILOT_TOOL_ARG_KEYS:
                raise ToolError("TOOL_FORBIDDEN", f"{name} is not available to the copilot")
            check_tool_access(actor.roles, name)
            check_tool_args(name, args)
            kwargs = {k: v for k, v in args.items() if k in COPILOT_TOOL_ARG_KEYS[name]}
            out = REGISTRY[name](db, actor.tenant_id, **kwargs)
            refs = list(out.get("evidence") or [])
            evidence.extend(refs)
            blocks.append(f"[{name}] {json.dumps(out, default=str)}")
            record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_TOOL_EXECUTED",
                         resource="ai_tool", resource_id=name,
                         after={"args": kwargs, "evidence": refs}, source="copilot", created_by=actor.sub)
        except ToolError as exc:
            notes.append(f"{name}: {exc.message}")
        except TypeError as exc:
            notes.append(f"{name}: bad args ({exc})")
    return blocks, evidence, notes


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
    """Configured + selectable providers. Never reveals a key — only whether
    one is present, and whether the caller must bring its own."""
    from ..services.ai_gateway import _active_provider, providers_catalog

    return envelope({"active": _active_provider(""), "available": providers_catalog()},
                    None, getattr(request.state, "request_id", ""))


@router.post("/ai/complete")
def run_complete(payload: CompleteIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> dict:
    rid = getattr(request.state, "request_id", "")
    _check_provider(payload)
    blocks, evidence, notes = _run_copilot_tools(payload.tools, actor, db, rid)
    system = payload.system
    if blocks:
        system = (system + "\n\n" if system else "") + (
            "GROUNDING DATA (verified from the tenant's live tables just now). "
            "Answer with only what it supports; cite the record ids.\n" + "\n\n".join(blocks)
        )
    try:
        result = complete(prompt=payload.prompt, system=system, provider=payload.provider,
                          provider_key=_provider_key_of(request, payload), model=payload.model)
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail={"code": "AI_PROVIDER_FAILED", "message": exc.message, "details": {"provider": exc.provider}}) from exc
    result = dict(result)
    result["evidence"] = evidence
    if notes:
        result["notes"] = notes
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_COMPLETED", resource="ai",
                 resource_id="complete", after={"provider": result["provider"], "model": result.get("model", ""),
                                                "tools": [t.name for t in payload.tools or []]}, source="api", created_by=actor.sub)
    db.commit()
    return envelope(result, None, rid)


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
    from ..services.purchase import PurchaseError, decide_approval as _decide

    row = db.execute(select(Approval).where(Approval.tenant_id == actor.tenant_id, Approval.id == approval_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if not row.resource.startswith("ai:"):
        raise HTTPException(status_code=422, detail="Not an AI-filed approval")
    try:
        status = _decide(db, tenant_id=actor.tenant_id, approver_sub=actor.sub,
                         approver_roles=set(actor.roles or ()), approval=row,
                         approve=payload.approve, reason=payload.reason)
    except PurchaseError as exc:
        code = {"APPROVAL_ROLE": 403, "APPROVAL_SOD": 403, "APPROVAL_ALREADY_DECIDED": 409,
                "APPROVAL_REASON_REQUIRED": 422}.get(exc.code, 422)
        raise HTTPException(status_code=code, detail={"code": exc.code, "message": exc.message}) from exc
    record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_APPROVAL_DECIDED", resource="ai_tool",
                 resource_id=approval_id, after={"approved": payload.approve}, reason=payload.reason.strip(),
                 approval=approval_id, source="api", created_by=actor.sub)
    db.commit()
    return envelope({"id": approval_id, "status": status}, None, getattr(request.state, "request_id", ""))


@router.post("/ai/stream")
def run_stream(payload: CompleteIn, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(db_for_actor)) -> Response:
    """Provider-side streaming with optional tool grounding: distinguishes real
    token streaming from the disabled fallback, and cites tool rows as evidence."""
    import json as _json

    from fastapi.responses import StreamingResponse as _SS

    from ..services.ai_gateway import AIGatewayError, _active_provider, complete as _complete, stream as _stream

    rid = getattr(request.state, "request_id", "")
    tenant, sub = actor.tenant_id, actor.sub

    _check_provider(payload)
    blocks, evidence, notes = _run_copilot_tools(payload.tools, actor, db, rid)
    system = payload.system
    if blocks:
        system = (system + "\n\n" if system else "") + (
            "GROUNDING DATA (verified from the tenant's live tables just now). "
            "Answer with only what it supports; cite the record ids.\n" + "\n\n".join(blocks)
        )

    provider_name = _active_provider(payload.provider)
    live = provider_name != "disabled"
    key = _provider_key_of(request, payload)

    def _events():  # type: ignore[no-untyped-def]
        from ..core.tenant import pinned_session
        from ..services.audit import record_event as _rec

        aggregated: list[str] = []
        try:
            if live:
                for delta in _stream(prompt=payload.prompt, system=system, provider=payload.provider,
                                     provider_key=key, model=payload.model):
                    aggregated.append(delta)
                    yield f"data: {_json.dumps({'delta': delta, 'streamed': True})}\n\n"
                answer = "".join(aggregated)
                evidence_payload = {"confidence": 0.55, "provider": provider_name,
                                    "model": payload.model or "", "evidence": evidence, "notes": notes,
                                    "requires_human_review": True, "requestId": rid, "streamed": True}
            else:
                result = _complete(prompt=payload.prompt, system=system, provider=payload.provider,
                                   provider_key=key, model=payload.model)
                answer = result.get("answer", "")
                yield f"data: {_json.dumps({'delta': answer, 'streamed': False})}\n\n"
                evidence_payload = {"confidence": result.get("confidence"), "provider": result.get("provider"),
                                    "model": result.get("model", ""), "evidence": evidence, "notes": notes,
                                    "requires_human_review": True, "requestId": rid, "streamed": False}
        except AIGatewayError as exc:
            yield f"data: {_json.dumps({'error': exc.message, 'provider': exc.provider, 'streamed': live})}\n\n"
            return

        yield f"data: [EVIDENCE] {_json.dumps(evidence_payload)}\n\n"
        sdb = None
        try:
            sdb = pinned_session(tenant)
            _rec(sdb, tenant_id=tenant, actor=sub, action="AI_COMPLETED", resource="ai",
                 resource_id="stream", after={"provider": provider_name, "chars": len(answer), "live": live},
                 source="api", created_by=sub)
            sdb.commit()
        except Exception:
            if sdb is not None:
                sdb.rollback()
        finally:
            if sdb is not None:
                sdb.close()

    return _SS(_events(), media_type="text/event-stream",
               headers={"X-Request-ID": rid, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
