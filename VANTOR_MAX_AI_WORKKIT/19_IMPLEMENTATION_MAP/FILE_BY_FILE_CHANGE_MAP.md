<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# File-by-File Change Map

| Source file | Current role | Required change focus | Verification |
|---|---|---|---|
| `backend/app/routers/purchase.py` | P2P endpoints | Replace duplicated auth/approval logic with shared command services; lock financial transitions; invoice approval via Approval row; ledger uniqueness | Unit + PG + concurrency + E2E |
| `backend/app/services/purchase.py` | Purchase rules | Make matcher canonical and cumulative; shared approval authority/policy | Unit + property + PG |
| `backend/app/services/matching.py` | Deterministic 11-dim matcher | Make this or a unified successor the single matcher used everywhere | Unit + integration |
| `backend/app/routers/catalog.py` | Budget/catalog | Atomic budget reservation; policy/configuration | PG concurrency |
| `backend/app/services/integration.py` | Webhook dispatch | Replace synchronous fanout with outbox/worker/retry/SSRF-safe client | Integration + chaos |
| `backend/app/routers/integrations.py` | Integration API | Permission, URL policy, replay/test flow | Security + E2E |
| `backend/app/services/document.py` | File validation/storage | Object-store abstraction, streaming metadata, stronger sniffing | Security + recovery |
| `backend/app/routers/documents.py` | Upload/extract/search | Streaming size enforcement, object storage, attachment validation, async pipeline | Upload + E2E + load |
| `backend/app/services/extract.py` | Parsers | ZIP/XML resource limits, parser isolation, OCR stage | Fuzz + bomb fixtures |
| `backend/app/models/document.py` | Document data model | Native pgvector + processing state/versioning | Migration + search tests |
| `backend/app/core/idempotency.py` | Request replay | Atomic key claim/in-flight state | Concurrency |
| `backend/app/core/ratelimit.py` | Abuse control | Async client/route-aware limits/failure policy | Load + outage |
| `backend/app/core/security.py` | OIDC | Non-blocking JWKS, cache/rotation observability, bounded claims | Auth tests + load |
| `backend/app/core/secheaders.py` | Browser security | CSP and production policy | Browser security |
| `backend/app/core/observe.py` | Telemetry | OTEL metrics/traces/logging | Two-replica trace test |
| `backend/app/routers/contracts.py` | Contract lifecycle | Permissioned transitions, signing verification, tenant timezone | Role matrix + E2E |
| `backend/app/routers/suppliers.py` | Supplier governance | Qualification/certification permissions and evidence checks | Role + E2E |
| `backend/app/routers/sourcing.py` | RFQ/award | Evaluation gate, currency, award concurrency | PG + E2E |
| `backend/app/routers/notifications.py` | Notification feed | Normalize broadcast read state for exact counts | Scale tests |
| `backend/app/routers/ai.py` | AI policy/tools | Immutable system policy, evidence gate, tool auth | Adversarial evals |
| `backend/app/services/ai_gateway.py` | AI provider adapter | Honest confidence, provider health, evidence contract, async/non-blocking client plan | Provider matrix |
| `frontend/app/copilot/page.tsx` | Copilot UI | Unique IDs, active turn state, BYOK workflow, evidence UX | Component + E2E |
| `frontend/components/ui.tsx` | UI primitives | Expand into full design system | Storybook/a11y/visual |
| `frontend/components/Shell.tsx` | App shell | Grade-5 IA, responsive navigation, icons, command palette | Visual + keyboard |
| `frontend/app/globals.css` | Design tokens | Replace inline styles with tokenized design system | Visual regression |
| `docker-compose.yml` | Local deployment | Keep local safe; create dedicated production deployment with private data services | Config/policy tests |
| `backend/Dockerfile` | API image | Non-root, hardened runtime, reproducible image | Container scan |
| `frontend/Dockerfile` | Web image | Non-root runtime, pinned build and runtime | Build/smoke |
| `worker/Dockerfile` | Worker image | Non-root, dependency pinning, graceful shutdown | Container/load |
| `worker/jobs.py` / `beat.py` | Background jobs | Workload identity, retries, job observability, real task registry | Fresh-deploy tests |

## Rule for unlisted files

The full source inventory is in `01_CURRENT_RE_AUDIT/SOURCE_FILE_INVENTORY.md`. Unlisted files are not automatically “safe” or “complete”. Before changing any file, the agent must inspect imports/callers/tests and add it to the implementation map when its behavior becomes part of a changed invariant.
