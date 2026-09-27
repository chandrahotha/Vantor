# Architecture Audit

Current design is a modular monolith plus frontend/worker. It is a reasonable foundation for a procurement SaaS because financial invariants remain centrally transactable. The main architecture weakness is not the monolith itself; it is **duplicate rule paths** and **side effects executed in request handlers**.

Target priorities: canonical domain commands, explicit aggregate locks, outbox/worker pattern, durable object storage, policy/authority services, and standardized evidence/audit model.
