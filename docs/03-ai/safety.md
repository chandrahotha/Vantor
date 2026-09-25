<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# AI Safety — Prompt-Injection Defense — VANTOR

**Status: `PLANNED`. All uploads/emails/supplier content = untrusted.**

## Defenses
1. **Delimit + label** untrusted content (doc/email/quote) vs system instructions; model never follows instructions inside evidence blocks.
2. **Typed tools + least privilege:** tool schemas validated; approval-gated side effects; spending-limit + role checks inside tools, not prompts.
3. **Output contract:** citations required; tool args echoed for review; secrets/PII redaction before model context.
4. **SSRF/file safety:** fetch allowlists, size/time caps, sandboxed OCR/parsers, no local-file exfiltration via tool args.
5. **Indirect injection:** quarantine suspicious phrases (`ignore previous instructions`, fake approvals, bank-change requests) → flag `REQUIRES HUMAN REVIEW` + audit.
6. **Evals + red-team:** injection suite in `../03-ai/evaluation.md` must pass before any AI release.

Incident: freeze tool, preserve audit, rotate exposed keys, post-mortem ADR.
