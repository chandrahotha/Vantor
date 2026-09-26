<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-003 — Free-first AI gateway (Ollama default)

- Context: owner requires free models/endpoints; production must not hard-depend on paid keys.
- Decision: `AI_PROVIDER` switch; Ollama local default; OpenCode + NVIDIA free endpoints as first-class options alongside Ollama; OpenRouter-free/Groq-free/HF fallbacks BYO-key; `disabled` deterministic mode. Evidence contract mandatory (`../03-ai/architecture.md`).
- Alternatives: OpenAI-only, Azure-only.
- Consequences: +zero-cost dev; +provider swap without core changes; −free-tier rate limits must be surfaced + budgeted per tenant.
