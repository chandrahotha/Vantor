# Target Architecture

## Target shape

Keep the modular monolith as the first target unless scale evidence requires extraction. The architecture should be:

`Next.js UI -> API/BFF -> domain application services -> repositories/query services -> PostgreSQL`

with:

- Redis for cache/rate-limit/ephemeral coordination;
- durable job queue for background work;
- object storage for documents;
- Keycloak/OIDC for identity;
- outbox/event table for external side effects;
- OpenTelemetry for telemetry.

Do not prematurely split into microservices. Separate concerns by transaction boundaries and domain ownership first.

## Non-negotiable boundaries

- Routers validate transport concerns only.
- Domain/application services own business invariants and transitions.
- Repositories own data access patterns where complexity justifies them.
- External integrations cannot execute before the source transaction is durably committed.
- AI is advisory and evidence-bound; deterministic engines remain authoritative for calculations.
