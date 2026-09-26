# Business Logic — AI Supplier Negotiation Simulator

1. Simulation state is isolated from live procurement systems.
2. The supplier persona is fictional/synthetic and its behavior is bounded by scenario configuration.
3. Offer arithmetic is deterministic.
4. LLM text cannot alter financial state without passing schema/range validation.
5. Buyer walk-away and policy constraints are hard boundaries.
6. Every simulated turn stores the exact prompt/run metadata and output schema version.
7. The simulator must clearly distinguish generated counterpart statements from source facts.
