<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Webhook Security

HMAC signatures must include stable event id, timestamp, canonical payload and version. Receiver should reject stale/replayed signatures and expose a replay-protection window. Sender must protect its own outbound surface with SSRF controls.

## Now implemented (2026-09-28)

The sender's side is the part that is implemented, and it is the part that can hurt a customer:
outbound requests go through `app.services.egress`, which resolves the hostname, refuses private,
loopback, link-local and cloud-metadata addresses, and then **pins the validated IP** while
preserving the original `Host` header and TLS SNI. Pinning matters because re-resolving at
connect time is the classic TOCTOU SSRF — the name is checked, then a second lookup returns
something else. Redirects are refused and dead-letter on first attempt. Every registered
destination is operator-registered, never caller-supplied.

The inbound receiver side (verifying a *provider's* signature over a callback we receive) is
implemented for the e-sign provider callback with an HMAC over timestamp and body, but the
replay-protection *window* is a fixed timestamp tolerance rather than a consumed-nonce store.
A signature inside the tolerance window can be replayed; for an e-sign status callback that is
acceptable because the handler is idempotent on the envelope id, and it is noted here rather
than claimed as fully implemented.
