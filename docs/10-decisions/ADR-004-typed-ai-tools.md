<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-004 — Typed AI tools, no raw SQL/shell

- Context: agents must act on procurement data without becoming an uncontrolled authority.
- Decision: allowlisted typed tools with in-tool permission checks; every call audited (`AI_TOOL_EXECUTED`); risk-tiered HITL.
- Alternatives: direct DB access, shell tool.
- Consequences: +least privilege + auditability; −more upfront tool design. See `../03-ai/safety.md`.
