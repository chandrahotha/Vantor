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
    try:
        result = complete(prompt=payload.prompt, system=payload.system, provider=payload.provider,
                          provider_key=_provider_key_of(request, payload), model=payload.model,
                          evidence=evidence, grounding="\n\n".join(blocks))
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail={"code": "AI_PROVIDER_FAILED", "message": exc.message, "details": {"provider": exc.provider}}) from exc
    result = dict(result)
    # The gateway already decided the evidence question and encoded the verdict in
    # `grounded` / `refusal_reason`. It is re-asserted here rather than trusted,
    # because this is the endpoint the product advertises: if an ungrounded answer
    # ever reached a 200 here, the claim on the landing page would be false again.
    if not result.get("grounded") and not result.get("evidence"):
        record_event(db, tenant_id=actor.tenant_id, actor=actor.sub, action="AI_REFUSED",
                     resource="ai", resource_id="complete",
                     after={"provider": result.get("provider", ""), "reason": result.get("refusal_reason", "")},
                     source="api", created_by=actor.sub)
        db.commit()
        raise HTTPException(status_code=422, detail={
            "code": "AI_NO_EVIDENCE",
            "message": result["answer"],
            "details": {"reason": result.get("refusal_reason", ""),
                        "provider": result.get("provider", ""),
                        # The notes explain *why* there is no evidence — a tool
                        # the copilot may not run, or a role that was refused.
                        # Dropping them would leave the caller with a refusal and
                        # no way to act on it.
                        "notes": notes,
                        "requiresHumanReview": True},
        })
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
    grounding = "\n\n".join(blocks)

    provider_name = _active_provider(payload.provider)
    live = provider_name != "disabled"
    key = _provider_key_of(request, payload)
    # A stream cannot un-send what it has already yielded, so the evidence
    # question is settled *before* the first token. VNT-014: the old code
    # streamed the whole answer and then shipped an `[EVIDENCE]` frame with
    # `evidence: []`, so the UI had a complete confident sentence and nothing
    # behind it. Refusing first means the client gets an explicit reason instead
    # of an answer it has to be told to distrust.
    grounded = bool([e for e in evidence if e])

    def _events():  # type: ignore[no-untyped-def]
        import json as _json

        from ..core.tenant import pinned_session
        from ..services.audit import record_event as _rec

        aggregated: list[str] = []
        if not grounded:
            reason = ("PROVIDER_DISABLED" if not live else "NO_EVIDENCE")
            message = ("UNKNOWN — no AI provider is configured in this environment."
                       if not live else
                       "I cannot answer that with evidence from your records. Run the "
                       "corresponding lookup tool first, or narrow the question to what "
                       "the data supports.")
            yield f"data: {_json.dumps({'error': message, 'code': 'AI_NO_EVIDENCE',
                                        'reason': reason, 'streamed': False})}\n\n"
            yield f"data: [EVIDENCE] {_json.dumps({'confidence': 0.0, 'provider': provider_name,
                                                  'model': payload.model or '', 'evidence': [],
                                                  'notes': notes, 'grounded': False,
                                                  'refusal_reason': reason,
                                                  'requires_human_review': True,
                                                  'requestId': rid, 'streamed': False})}\n\n"
            _audit(_rec, pinned_session, tenant, sub, rid, provider_name,
                   action="AI_REFUSED", reason=reason)
            return

        try:
            for delta in _stream(prompt=payload.prompt, system=payload.system,
                                 provider=payload.provider, provider_key=key,
                                 model=payload.model):
                aggregated.append(delta)
                yield f"data: {_json.dumps({'delta': delta, 'streamed': True})}\n\n"
            answer = "".join(aggregated)
            evidence_payload = {"confidence": 0.55, "provider": provider_name,
                                "model": payload.model or "", "evidence": evidence,
                                "notes": notes, "grounded": True, "refusal_reason": "",
                                "requires_human_review": True, "requestId": rid,
                                "streamed": True}
        except AIGatewayError as exc:
            yield f"data: {_json.dumps({'error': exc.message, 'provider': exc.provider, 'streamed': True})}\n\n"
            return

        yield f"data: [EVIDENCE] {_json.dumps(evidence_payload)}\n\n"
        _audit(_rec, pinned_session, tenant, sub, rid, provider_name,
               action="AI_COMPLETED", answer=answer)

    return _SS(_events(), media_type="text/event-stream",
               headers={"X-Request-ID": rid, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _audit(record_event, session_factory, tenant: str, sub: str, rid: str,
           provider_name: str, *, action: str, reason: str = "", answer: str = "") -> None:
    """Best-effort audit for a streamed turn.

    A failure to write the audit must not break the stream the caller is reading,
    so this swallows and rolls back rather than raising.
    """
    db = None
    try:
        db = session_factory(tenant)
        record_event(db, tenant_id=tenant, actor=sub, action=action, resource="ai",
                     resource_id="stream",
                     after={"provider": provider_name, "reason": reason,
                            "chars": len(answer)},
                     source="api", created_by=sub)
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
    finally:
        if db is not None:
            db.close()
