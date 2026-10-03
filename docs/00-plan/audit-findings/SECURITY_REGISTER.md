<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../BRAIN.md) · [Docs index](../../README.md)

# Security Register

High-priority security items are VNT-007, VNT-034, VNT-036 and the broader hardening items VNT-010/011/012/031/032. The agent must also perform a fresh code-level threat review of authentication, authorization, tenant boundaries, file parsing, outbound HTTP, browser security, secrets, dependencies and logging after implementing the listed fixes.

The threat model is in [`docs/04-security/threat-model.md`](../../04-security/threat-model.md). Do not close a security item solely because a static scanner is green.
