<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Webhook Security

HMAC signatures must include stable event id, timestamp, canonical payload and version. Receiver should reject stale/replayed signatures and expose a replay-protection window. Sender must protect its own outbound surface with SSRF controls.
