"""Catalog + budgets + signatures — global-parity models (Ariba/Coupa/Ivalua checklist).

CatalogItem: buyer-managed purchasables (guided buying) that prefill
requisition/PO lines with validated UOM + reference prices. No spot-buy fakery:
every line still validates against supplier + budget rules downstream.

Budget: per (category_id, period YYYY-MM) ceiling in minor units. PO approval
performs a hard check: sum(approved+sent POs' lines in scope) + this PO must fit.
Over-budget => 422 with the numbers (never silent squeeze).

ContractSignature: sign-off records. Internal method = authenticated user click
(actor + timestamp + hash of contract snapshot). External e-sign providers plug
in via the integrations adapter interface; the record stores provider + envelope
id, and VNT-023 added the state that makes the claim checkable: an e-sign row
is `pending` until a provider callback or status poll confirms it, and the
database refuses an e-sign row that is `signed` without a `verified_at`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, tenant_ref


class CatalogItem(Base, TenantMixin):
    __tablename__ = "catalog_items"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    uom: Mapped[str] = mapped_column(String(16), default="each", nullable=False)
    ref_price_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_catalog_tenant_code"),
        Index("ix_catalog_tenant_cat", "tenant_id", "category_id"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("catalog_items", "category_id", "categories"),
    )


class Budget(Base, TenantMixin):
    __tablename__ = "budgets"

    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    ceiling_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "category_id", "period", name="uq_budget_tenant_cat_period"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("budgets", "category_id", "categories"),
    )


class ContractSignature(Base, TenantMixin):
    """A sign-off record. VNT-023: this had no state at all.

    An e-signature row recorded a caller-supplied `provider` and `envelope_id`
    and nothing else, so the API returned 201 and wrote a hash-chained, audited
    "signed" record for a claim nobody had verified. There was no way to record
    the provider's answer, which means there was no way to check it.

    `status` is therefore the point of the row: `pending` when an envelope is
    dispatched, `signed` only once the provider has confirmed (by inbound
    callback or by an outbound status poll), and `declined`/`voided` for the
    other terminal answers. A signature may only be created `pending` for
    `esign`; `internal` is an authenticated click and is `signed` immediately.
    `verified_at` and `provider_payload` record when and how it was confirmed,
    so the audit trail answers "on whose word" as well as "when".
    """

    __tablename__ = "contract_signatures"

    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    signer: Mapped[str] = mapped_column(String(256), nullable=False)
    method: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)  # internal|esign
    provider: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    envelope_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # VNT-023. `verified_at` answers *when*; this answers *on whose word*. Without
    # it, a signature confirmed by a signed callback from the provider is
    # indistinguishable from one an operator typed into an authenticated form, and
    # a dispute over a contract has no way to resolve that question. Values:
    #   provider_callback     - HMAC-verified callback from the e-sign provider
    #   manual_reconciliation - a human asserted it, with a recorded reason
    #   internal_click        - `method='internal'`; an authenticated click, not a
    #                           provider claim at all
    verified_via: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    # The provider's own response, verbatim. Kept so a dispute can be settled
    # against what the provider actually said rather than against our summary.
    provider_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # B-19. The digest of the last accepted provider callback, over
    # `{timestamp}.{body}` under the provider's secret. The MAC covered a
    # timestamp rather than a consumed nonce, so a captured callback could be
    # re-sent for as long as that timestamp was fresh: the state transition was
    # idempotent, but every agreeing replay was still *accepted*. This is the
    # consumed nonce, stored on the row the callback is scoped to — one envelope
    # per provider is already the uniqueness constraint above, so the row IS the
    # nonce's scope and a separate table would be a second lookup for the same
    # fact. A replayed capture matches the digest and is refused before the
    # terminal-state check; a genuinely fresh callback has a new timestamp and
    # therefore a new digest, so a provider retry is not a replay.
    last_callback_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_sig_tenant_contract", "tenant_id", "contract_id"),
        # One open envelope per provider: re-dispatching the same envelope would
        # create a second pending claim for one document.
        #
        # This is a *partial* index, restricted to e-sign rows, and it has to be.
        # `provider` and `envelope_id` are NOT NULL with a `""` default, so every
        # internal signature carries the literal pair ('', ''). A plain unique
        # constraint over (tenant_id, provider, envelope_id) therefore collides on
        # the *second* internal signature in a tenant — a contract signed by its
        # drafter and then by legal would be rejected by the database for no
        # reason a reader of the schema could predict. Internal signatures are
        # legitimately repeatable (one row per signer); envelope uniqueness is
        # only a meaningful claim for rows that actually have an envelope.
        Index(
            "uq_sig_tenant_provider_envelope",
            "tenant_id",
            "provider",
            "envelope_id",
            unique=True,
            postgresql_where=text("method = 'esign'"),
            sqlite_where=text("method = 'esign'"),
        ),
        CheckConstraint("method in ('internal','esign')", name="ck_signature_method"),
        CheckConstraint("status in ('pending','signed','declined','voided')", name="ck_signature_status"),
        CheckConstraint(
            # A signed row must record when it was confirmed and on whose word.
            # `verified_via` is the load-bearing half: `verified_at` alone cannot
            # distinguish a provider's signed callback from an operator's
            # assertion, which is the question a contract dispute actually asks.
            "verified_via in ('','provider_callback','manual_reconciliation','internal_click')",
            name="ck_signature_verified_via"),
        CheckConstraint(
            # An e-sign row is only `signed` if the provider confirmed it, and an
            # internal row is `signed` the moment it is written. This is the
            # database refusing to hold a claim nobody verified.
            "method = 'internal' or status <> 'signed' or verified_at IS NOT NULL",
            name="ck_signature_esign_verified"),
        CheckConstraint(
            # ...and a signed e-sign row must also say *how* it was verified. An
            # esign row that reached `signed` with no `verified_via` is a claim
            # that arrived from nowhere.
            "method = 'internal' or status <> 'signed' or verified_via <> ''",
            name="ck_signature_esign_verified_via"),

        # Composite, tenant-carrying links — this table is itself linked by a composite reference.
        tenant_ref("contract_signatures", "contract_id", "contracts"),
    )
