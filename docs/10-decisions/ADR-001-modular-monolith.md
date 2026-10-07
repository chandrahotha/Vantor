<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-001 - Modular monolith first

- Context: 5 repos merging; team small; no load data justifying distributed system.
- Decision: single deployable API with strict module boundaries (`../02-architecture/system.md`).
- Alternatives: microservices per domain, serverless-per-module.
- Consequences: +simple ops/deploy; +single transactions; −must enforce boundaries via lint/tests; extract services later only with measured need.
