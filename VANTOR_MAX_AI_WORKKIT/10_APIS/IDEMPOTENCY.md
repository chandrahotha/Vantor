<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Idempotency

Every externally retriable mutation should accept `Idempotency-Key`. Claim atomically before execution; store request hash, status, response metadata and TTL. Mismatched reuse of a key with different payload returns conflict.
