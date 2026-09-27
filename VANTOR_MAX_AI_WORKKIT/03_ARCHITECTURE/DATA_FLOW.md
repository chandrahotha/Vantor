<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Data Flow

## Procure-to-pay

Requisition -> approval(s) -> PO -> approval(s) -> send -> receipt(s) -> invoice -> match -> approval -> actual spend -> payment/closed.

For each transition, audit the actor, authority, reason, timestamp, source request ID, and affected business values.

## External side effects

Business transaction -> DB commit -> outbox event -> worker -> adapter -> external system -> delivery record.

Never hold the API transaction open while waiting for a remote partner.
