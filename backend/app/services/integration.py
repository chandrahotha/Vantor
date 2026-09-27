"""Integration service — adapter interface + HMAC-signed webhook dispatch.

Adapter contract (implement `Adapter.send(event, payload)`; core never imports
a provider SDK — adapters live here behind the interface):
- `LoggingAdapter` (reference): records to audit, proves the contract end-to-end.
- Real ERP/email adapters arrive as separate modules implementing `Adapter`.

Webhooks: HMAC-SHA256 over the canonical payload with the endpoint secret
(resolved from env vault refs at send time, never stored).

VNT-008. Delivery used to be a synchronous `httpx.post` inside the request, with
a 20-second budget across all endpoints and nothing after that — a slow or dead
receiver held the caller's request open, and a failure was recorded once and
never retried. `MAX_ATTEMPTS = 5` was defined and referenced nowhere. A signed
payload that never arrived is indistinguishable to the receiver from one that was
never sent, so an at-least-once guarantee needs a durable queue.

Dispatch is now a **durable outbox**: `fanout` enqueues one `WebhookDelivery` per
endpoint in state `pending` and returns immediately, and the worker
(`worker/jobs.py::deliver`) drains the queue with exponential backoff, a bounded
attempt count, and a dead-letter state that is replayable on demand via
`POST /webhooks/deliveries/{id}/replay`. `send` remains available for callers
that genuinely need synchronous delivery (the `test` endpoint), and uses exactly
the same retry accounting so a test ping cannot tell you "delivered" while the
real path is silently broken.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.integration import DELIVERY_STATUSES, WebhookDelivery, WebhookEndpoint
from .egress import EgressError, build_pinned_request, validate_url

TIMEOUT_S = 10.0
MAX_ATTEMPTS = 5

#: Exponential backoff, with full jitter, between delivery attempts. Jitter is not
#: decoration: without it, a receiver that was briefly unreachable receives every
#: queued delivery in the same millisecond when it returns.
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 300.0


def backoff_seconds(attempts: int) -> float:
    """Delay before attempt number `attempts + 1`."""
    raw = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** max(0, attempts - 1)))
    return raw * (0.5 + random.random() / 2)  # noqa: S311 — jitter, not crypto


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


def _deliver_once(url: str, *, body: str, headers: dict) -> tuple[bool, str]:
    """One HTTP attempt with the address pinned to what was validated.

    VNT-007. `assert_safe_to_dial` re-resolves the host immediately before the
    connection, so a DNS rebind between endpoint registration and delivery
    cannot substitute a different destination. Validation alone is not enough:
    the name is only safe at the instant it was checked.

    The pinning is not optional bookkeeping. An earlier version of this function
    called `assert_safe_to_dial`, discarded the address it returned, and then
    posted to `target.url` — which re-resolves the name, so the socket opened
    wherever DNS pointed at that instant. The comment claimed a guarantee the code
    did not provide, which is the worst combination available: the audit trail
    said the rebinding window was closed and it was open. `build_pinned_request`
    dials the validated address directly and carries the hostname through in the
    `Host` header and in the TLS SNI, so the certificate is still verified
    against the real name.
    """
    target = validate_url(url)
    request = build_pinned_request(
        target, method="POST", content=body, headers=headers)
    # `follow_redirects=False` is explicit rather than inherited from a library
    # default, because a 302 to `http://169.254.169.254/` is the easiest SSRF in
    # the world and the default is one library upgrade away from changing.
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False) as client:
        response = client.send(request)
    if 300 <= response.status_code < 400:
        return False, f"redirect refused ({response.status_code}) - delivery must terminate at the registered URL"
    response.raise_for_status()
    return True, ""


def _attempt_delivery(delivery: WebhookDelivery, *, endpoint_url: str, secret_ref: str,
                      body: str, event: str) -> tuple[str, str]:
    """Attempt one delivery and record the outcome. Returns `(status, error)`."""
    secret = resolve_secret(secret_ref)
    if not secret:
        delivery.attempts += 1
        delivery.status, delivery.last_error, delivery.next_attempt_at = (
            "dead", "no resolvable signing secret for this endpoint", None)
        return "dead", delivery.last_error
    delivery.attempts += 1
    try:
        ok, reason = _deliver_once(
            endpoint_url, body=body,
            headers={"Content-Type": "application/json", "X-Vantor-Event": event,
                     "X-Vantor-Signature": f"sha256={sign(secret, body)}"})
    except EgressError as exc:
        # A refused destination is permanent: retrying will not make
        # 169.254.169.254 reachable. Dead-letter it immediately rather than
        # burning five attempts on a guaranteed failure.
        delivery.status, delivery.last_error, delivery.next_attempt_at = (
            "dead", f"egress refused: {exc.code} {exc.message}"[:500], None)
        return "dead", delivery.last_error
    except Exception as exc:  # noqa: BLE001 — recorded, never raised
        ok, reason = False, f"{type(exc).__name__}: {exc}"[:500]
    if ok:
        delivery.status, delivery.last_error, delivery.next_attempt_at = "delivered", "", None
        return "delivered", ""
    if delivery.attempts < MAX_ATTEMPTS and _is_retryable(reason):
        delivery.status, delivery.last_error = "pending", reason[:500]
        return "pending", reason[:500]
    delivery.status, delivery.last_error, delivery.next_attempt_at = "dead", reason[:500], None
    return "dead", reason[:500]


def _is_retryable(reason: str) -> bool:
    """Connection problems are worth another attempt; client errors generally are not."""
    lowered = reason.lower()
    permanent_markers = (
        "400 bad request", "401 unauthorized", "403 forbidden", "404 not found",
        "405 method not allowed", "410 gone", "422 unprocessable",
        "redirect refused", "egress refused",
    )
    return not any(marker in lowered for marker in permanent_markers)


def enqueue(db: Session, *, tenant_id: str, event: str, payload: dict,
            endpoints: list[WebhookEndpoint], body: str) -> list[dict]:
    """Durable enqueue. One `pending` row per endpoint; no network call."""
    out: list[dict] = []
    for ep in endpoints:
        delivery = WebhookDelivery(tenant_id=tenant_id, created_by="", updated_by="",
                                   endpoint_id=ep.id, event=event, payload=payload,
                                   status="pending", attempts=0, body=body)
        db.add(delivery)
        out.append({"endpoint": ep.id, "status": "pending", "url": ep.url})
    db.flush()
    return out


def drain(db: Session, *, tenant_id: str = "", limit: int = 50) -> list[dict]:
    """Attempt due deliveries. Called by the worker; safe to call in a loop.

    Rows are selected with `FOR UPDATE SKIP LOCKED` where the dialect supports
    it, so several workers can drain concurrently without two of them picking up
    the same delivery and signing it twice.
    """
    now = datetime.now(timezone.utc)
    # Every filter before the limit. Filtering after it is at best a warning and
    # at worst a silently unfiltered scan, and it makes the tenant predicate
    # depend on where the call happens to put it.
    stmt = select(WebhookDelivery).where(
        WebhookDelivery.status == "pending",
        (WebhookDelivery.next_attempt_at.is_(None))
        | (WebhookDelivery.next_attempt_at <= now),
    )
    if tenant_id:
        stmt = stmt.where(WebhookDelivery.tenant_id == tenant_id)
    stmt = stmt.order_by(WebhookDelivery.created_at, WebhookDelivery.id).limit(limit)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    rows = list(db.execute(stmt).scalars())
    results: list[dict] = []
    for delivery in rows:
        endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or endpoint.status != "active":
            delivery.status, delivery.last_error, delivery.next_attempt_at = (
                "dead", "endpoint deleted or deactivated", None)
            results.append({"delivery": delivery.id, "status": "dead"})
            continue
        status, error = _attempt_delivery(delivery, endpoint_url=endpoint.url,
                                          secret_ref=endpoint.secret_ref,
                                          body=delivery.body or "", event=delivery.event)
        if status == "pending":
            delivery.next_attempt_at = (
                datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds(delivery.attempts)))
        results.append({"delivery": delivery.id, "status": status,
                        "attempts": delivery.attempts, "error": error})
    db.commit()
    return results


def fanout(db: Session, *, tenant_id: str, event: str, payload: dict) -> list[dict]:
    """Durably enqueue `event` for every active subscribed endpoint.

    This no longer performs a network call. A caller gets `pending` rows it can
    rely on being attempted, and the worker decides when. That is the difference
    between "the receiver may or may not have it" and at-least-once.
    """
    endpoints = list(db.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.status == "active")).scalars())
    body = canonical({"event": event, "tenant_id": tenant_id, "at": int(time.time()), "data": payload})
    seen: set[str] = set()
    targets: list[WebhookEndpoint] = []
    skipped: list[dict] = []
    for ep in endpoints:
        if ep.events and event not in ep.events:
            continue
        if ep.url in seen:
            skipped.append({"endpoint": ep.id, "status": "skipped_duplicate", "url": ep.url})
            continue
        seen.add(ep.url)
        targets.append(ep)
    # The skipped reports come first so the caller sees, in order, that a
    # duplicate registration was noticed and deliberately not queued.
    return skipped + enqueue(db, tenant_id=tenant_id, event=event, payload=payload,
                             endpoints=targets, body=body)


def deliver_now(db: Session, *, tenant_id: str, endpoint_id: str, event: str,
                payload: dict) -> dict:
    """Synchronous single-endpoint delivery with the same retry accounting.

    Used by `POST /webhooks/test` only. It exists so a tenant can prove their
    receiver and secret work; it deliberately does not enqueue, because a test
    ping that waited for a worker would tell the operator nothing.
    """
    endpoint = db.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.id == endpoint_id)).scalar_one_or_none()
    if endpoint is None:
        return {"status": "failed", "error": "endpoint not found"}
    body = canonical({"event": event, "tenant_id": tenant_id, "at": int(time.time()), "data": payload})
    delivery = WebhookDelivery(tenant_id=tenant_id, created_by="", updated_by="",
                               endpoint_id=endpoint.id, event=event, payload=payload,
                               status="pending", attempts=0, body=body)
    db.add(delivery)
    db.flush()
    status, error = _attempt_delivery(delivery, endpoint_url=endpoint.url,
                                      secret_ref=endpoint.secret_ref, body=body, event=event)
    db.commit()
    return {"delivery": delivery.id, "status": status, "attempts": delivery.attempts,
            "error": error, "url": endpoint.url}


def replay(db: Session, *, tenant_id: str, delivery_id: str) -> dict:
    """Return a dead-lettered delivery to the queue with its attempt count reset.

    The attempt counter resets deliberately: a receiver that was wrong is
    usually right now, and without a reset a replayed row is immediately
    dead-lettered again on its first failure.
    """
    delivery = db.execute(select(WebhookDelivery).where(
        WebhookDelivery.tenant_id == tenant_id, WebhookDelivery.id == delivery_id)).scalar_one_or_none()
    if delivery is None:
        return {"status": "failed", "error": "delivery not found"}
    if delivery.status == "delivered":
        return {"status": "failed", "error": "delivery already succeeded; replay would duplicate a signed payload"}
    delivery.status, delivery.attempts, delivery.last_error = "pending", 0, ""
    delivery.next_attempt_at = None
    db.commit()
    return {"status": "pending", "delivery": delivery.id, "event": delivery.event}


assert set(("pending", "delivered", "failed", "dead")) <= DELIVERY_STATUSES, (
    "integration.DELIVERY_STATUSES must cover the durable queue states; "
    f"got {sorted(DELIVERY_STATUSES)}")

