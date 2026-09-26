# Rule Catalog — AI Supplier Negotiation Simulator

- R10-001: Simulation cannot invoke production procurement write tools.
- R10-002: Buyer walk-away limits are hard simulator constraints.
- R10-003: Offer arithmetic is deterministic and independent of LLM prose.
- R10-004: Supplier persona facts are scenario-defined fictional assumptions, never presented as verified supplier facts.
- R10-005: Evidence pack is read-only and sanitized before model exposure.
- R10-006: Each generated response records model/run/prompt/schema metadata.
- R10-007: Prompt injection in evidence must not alter simulator tools, system policy or approval state.
- R10-008: Scoring uses a fixed versioned rubric and deterministic event ledger inputs.
- R10-009: Simulation and debrief output must clearly label generated content.
- R10-010: Replay of a saved session with the same deterministic settings must reproduce commercial calculations even if generated language differs.

Each rule is versioned, testable and mapped to at least one golden test. Rules are data/engine logic, never hidden in an LLM prompt.
