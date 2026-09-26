"""Integration service — adapter interface + HMAC-signed webhook dispatch.

Adapter contract (implement `Adapter.send(event, payload)`; core never imports
a provider SDK — adapters live here behind the interface):
- `LoggingAdapter` (reference): records to audit, proves the contract end-to-end.
- Real ERP/email adapters arrive as separate modules implementing `Adapter`.

Webhooks: HMAC-SHA256 over the canonical payload with the endpoint secret
(resolved from env vault refs at send time, never stored). Dispatch is
synchronous in-request for Wave 1 (worker queue in Wave 2); failures are
recorded as failed deliveries with the error — never raised to the caller.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.integration import WebhookDelivery, WebhookEndpoint

TIMEOUT_S = 10.0
MAX_ATTEMPTS = 5


class Adapter:
    name = "base"

    def send(self, event: str, payload: dict) -> dict:
        raise NotImplementedError


class LoggingAdapter(Adapter):
    """Reference adapter — proves the interface without any external call."""
    name = "logging"

    def __init__(self, db: Session, tenant_id: str, actor: str):
        from ..services.audit import record_event

        self._db = db
        self._tenant = tenant_id
        self._actor = actor
        self._record = record_event

    def send(self, event: str, payload: dict) -> dict:
        self._record(self._db, tenant_id=self._tenant, actor=self._actor, action="INTEGRATION_SENT",
                     resource="integration", after={"adapter": self.name, "event": event}, source="api", created_by=self._actor)
        return {"adapter": self.name, "event": event, "accepted": True}


ADAPTERS: dict[str, type[Adapter]] = {"logging": LoggingAdapter}


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def resolve_secret(ref: str) -> str:
    # Vault refs look like `env:NAME`; anything else is refused (never a raw secret).
    if ref.startswith("env:"):
        return os.getenv(ref[4:], "")
    return ""


#: Wall-clock budget for one fanout, across all endpoints. Each delivery is a
#: synchronous HTTP call with its own 10s timeout, so a tenant with several dead
#: endpoints held the caller's request open for 10s * n. The remainder is
#: reported as `deferred` rather than silently dropped.
FANOUT_BUDGET_S = 20.0


def fanout(db: Session, *, tenant_id: str, event: str, payload: dict) -> list[dict]:
    """Deliver `event` to all active subscribed endpoints; returns per-endpoint results.

    One delivery per distinct URL. `webhook_endpoints.url` carries no unique
    constraint (adding one is a schema change that could fail on existing rows),
    so a tenant that registered the same URL twice previously received the same
    signed payload twice — a duplicate side effect for any consumer that is not
    idempotent. Duplicates are collapsed here and the extra registration is
    reported as `skipped_duplicate` instead of being delivered.
    """
    out: list[dict] = []
    endpoints = list(db.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.status == "active")).scalars())
    body = canonical({"event": event, "tenant_id": tenant_id, "at": int(time.time()), "data": payload})
    deadline = time.monotonic() + FANOUT_BUDGET_S
    seen_urls: set[str] = set()
    for ep in endpoints:
        if ep.events and event not in ep.events:
            continue
        if ep.url in seen_urls:
            out.append({"endpoint": ep.id, "status": "skipped_duplicate", "url": ep.url})
            continue
        seen_urls.add(ep.url)
        out_of_budget = time.monotonic() >= deadline
        secret = resolve_secret(ep.secret_ref)
        delivery = WebhookDelivery(tenant_id=tenant_id, created_by="", updated_by="", endpoint_id=ep.id,
                                   event=event, payload=payload, status="queued", attempts=0)
        db.add(delivery)
        db.flush()
        if out_of_budget:
            # Recorded rather than dropped: a deferred attempt is a fact about
            # this fanout, and the audit trail should carry it.
            delivery.status = "deferred"
            delivery.last_error = f"fanout budget of {FANOUT_BUDGET_S:.0f}s exhausted before this endpoint"
            out.append({"endpoint": ep.id, "status": "deferred", "url": ep.url, "detail": delivery.last_error})
            continue
        if not secret or not ep.url.startswith("https://"):
            delivery.status, delivery.last_error = "failed", "no secret or non-https url — refused"
            out.append({"endpoint": ep.id, "status": "failed"})
            continue
        try:
            r = httpx.post(ep.url, content=body,
                           headers={"Content-Type": "application/json", "X-Vantor-Event": event,
                                    "X-Vantor-Signature": f"sha256={sign(secret, body)}"},
                           timeout=TIMEOUT_S)
            r.raise_for_status()
            delivery.status, delivery.attempts = "delivered", 1
            out.append({"endpoint": ep.id, "status": "delivered"})
        except Exception as exc:  # noqa: BLE001 — recorded, never raised
            delivery.status, delivery.attempts, delivery.last_error = "failed", 1, f"{type(exc).__name__}: {exc}"[:500]
            out.append({"endpoint": ep.id, "status": "failed"})
    db.flush()
    return out
