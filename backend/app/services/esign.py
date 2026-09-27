"""E-signature provider callbacks — the verified half of VNT-023.

The gap this closes
------------------
`POST /contracts/{id}/sign/verify` let an authenticated legal reviewer apply a
provider's answer to a signature row. That is a *trusted operator* asserting an
outcome, not the provider asserting it. Nothing tied the resulting `signed` row to
anything the e-sign provider had actually said, so the platform could record a
completed, hash-chained, audited signature for an envelope that was never signed
by anyone. A `Buyer` could not do it, but a `Legal Reviewer` could, and that is
not the same thing as the provider confirming.

This module is the other path: the provider speaks, and the platform checks that
it is the provider before believing it.

Design decisions that are not obvious
------------------------------------
**The callback is not tenant-scoped in the request.** A provider's webhook
carries the envelope id, not our tenant id, so the row has to be found by
`(provider, envelope_id)` across all tenants. That is safe because a provider's
envelope ids are unique to that provider, but it is *not* safe to assume: if a
provider ever reused an id, two tenants would have a row matching. The lookup
therefore returns every match and **refuses when there is more than one**, rather
than picking the first. Silently choosing one would let a forged callback for
tenant A's envelope land on tenant B's contract.

**The signature covers a timestamp, and the timestamp is checked.** Signing the
body alone makes any captured callback replayable forever: an attacker who
observes one `signed` callback can re-send it after a later `voided`, or re-send
it against a different envelope id. So the signed material is
`{timestamp}.{body}`, and a timestamp outside `REPLAY_WINDOW_S` is refused.
Providers that cannot send a timestamp should not be wired to this endpoint.

**The comparison is constant-time.** `hmac.compare_digest`, not `==`. A byte-wise
comparison of a MAC leaks how many leading bytes were correct, which is enough to
recover a MAC one byte at a time.

**An unconfigured provider cannot be called.** `secret_for` resolves an
`env:` reference and returns nothing when it is unset; the callback then refuses
rather than accepting an unsigned body. "No secret configured" must never mean
"verification skipped".

**The secret is resolved per request and never stored.** Same `env:`-only
convention as the outbound webhook signing, so a deployment's signing secret
lives in the environment and not in the database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.catalog import ContractSignature

#: How far a callback's timestamp may drift before it is refused. Five minutes
#: absorbs ordinary clock skew between the provider and this host and nothing
#: more: a wider window is a wider replay window.
REPLAY_WINDOW_S = 300

#: Statuses a provider is allowed to report. Anything else is a provider we do
#: not understand, and guessing at it would write an invented value into an
#: audited column.
ALLOWED_STATUSES = frozenset({"signed", "declined", "voided"})

#: Environment variable holding each provider's shared secret. `docusign` ->
#: `ESIGN_SECRET_DOCUSIGN`. Upper-cased and non-alphanumerics collapsed to `_`,
#: so a provider name like "DocuSign EU" still has one obvious variable.
_SECRET_ENV = "ESIGN_SECRET_{}"


class CallbackError(ValueError):
    """The callback is not trustworthy. `code` is stable and safe to branch on.

    Every refusal is a 401 or 422 and says which check failed, so a deployment can
    be debugged without reading this file. None of them reveal whether a given
    envelope exists — that is a different question, answered with the same 401,
    so the endpoint cannot be used to enumerate contracts.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def secret_env_name(provider: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in (provider or "").strip().lower())
    return _SECRET_ENV.format(slug.upper() or "DEFAULT")


def secret_for(provider: str) -> str:
    """The provider's shared secret, or `""` when none is configured."""
    return os.getenv(secret_env_name(provider), "").strip()


def _constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def verify_callback(provider: str, timestamp: str, body: bytes, signature: str) -> None:
    """Authenticate a callback, or raise `CallbackError`.

    Order matters. The secret is checked for presence first, then the timestamp
    window, then the MAC. A missing secret must not fall through to a MAC
    comparison against an empty string, which an attacker trivially satisfies.
    """
    secret = secret_for(provider)
    if not secret:
        raise CallbackError(
            "ESIGN_PROVIDER_NOT_CONFIGURED",
            f"No shared secret is configured for provider {provider!r}; "
            f"set {secret_env_name(provider)}",
        )

    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise CallbackError("ESIGN_TIMESTAMP_INVALID", "Timestamp is not an integer") from None

    now = int(time.time())
    if abs(now - sent_at) > REPLAY_WINDOW_S:
        raise CallbackError(
            "ESIGN_TIMESTAMP_STALE",
            f"Callback timestamp is outside the {REPLAY_WINDOW_S}s replay window",
        )

    expected = hmac.new(
        secret.encode(), f"{sent_at}.".encode() + body, hashlib.sha256
    ).hexdigest()
    if not _constant_time_equal(expected, (signature or "").strip()):
        raise CallbackError("ESIGN_SIGNATURE_INVALID", "Callback signature does not match")


def apply_callback(
    db: Session,
    *,
    provider: str,
    envelope_id: str,
    status: str,
    payload: dict,
) -> tuple[ContractSignature, str]:
    """Apply a verified provider answer to the matching signature row.

    Returns `(row, previous_status)` so the caller can record the transition.

    Raises `CallbackError` for an unknown envelope, an ambiguous one, a status we
    do not model, or a terminal row that is being changed to a different terminal
    status.
    """
    target = (status or "").strip().lower()
    if target not in ALLOWED_STATUSES:
        raise CallbackError(
            "ESIGN_STATUS_UNKNOWN",
            f"Provider reported {status!r}; expected one of {sorted(ALLOWED_STATUSES)}",
        )
    envelope = (envelope_id or "").strip()
    if not envelope:
        raise CallbackError("ESIGN_ENVELOPE_MISSING", "envelope_id is required")

    matches = list(
        db.execute(
            select(ContractSignature)
            .where(
                ContractSignature.provider == provider,
                ContractSignature.envelope_id == envelope,
            )
            .with_for_update()
        ).scalars()
    )
    if not matches:
        raise CallbackError("ESIGN_ENVELOPE_NOT_FOUND", "No signature matches that envelope")
    if len(matches) > 1:
        # Refuse rather than pick. A callback that matches two tenants' rows is
        # either a provider bug or an attack, and choosing the first row would
        # apply it to whichever tenant happened to be created first.
        raise CallbackError(
            "ESIGN_ENVELOPE_AMBIGUOUS",
            "The envelope matches more than one signature; refusing to guess",
        )

    sig = matches[0]
    if sig.status in {"signed", "declined", "voided"} and target != sig.status:
        raise CallbackError(
            "ESIGN_ALREADY_TERMINAL",
            f"This envelope is already {sig.status}",
        )

    before = sig.status
    sig.status = target
    sig.provider_payload = payload
    sig.verified_via = "provider_callback"
    if target == "signed":
        sig.verified_at = datetime.now(timezone.utc)
    sig.updated_by = f"provider:{provider}"
    db.flush()
    return sig, before


def parse_body(raw: bytes) -> dict:
    """The provider's JSON body, or a refusal.

    Parsed by the caller from the raw bytes *before* verification so that the MAC
    is checked over exactly what arrived, not over a re-serialisation of it.
    """
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CallbackError("ESIGN_BODY_INVALID", "Callback body is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise CallbackError("ESIGN_BODY_INVALID", "Callback body must be a JSON object")
    return parsed
