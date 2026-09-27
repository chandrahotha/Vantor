# Master Findings Register

The table below is the re-audit source of truth for the current archive. “Verified” means directly established from source or an executed reproduction. “Strong static finding” is an evidence-backed architecture/code risk that still requires a production-style test to prove exploitability. No finding below should be ignored because a unit test is green.

| ID | Severity | Category | Title | Location | Status | Confidence |
|---|---|---|---|---|---|---|
| VNT-001 | High | Financial integrity | Live invoice approval checks only the current invoice quantity, not cumulative invoiced quantity. | `backend/app/services/purchase.py:123-153 (`three_way_match`); backend/app/routers/purchase.py:455-480 (`approve_invoice`)` | Verified | High |
| VNT-002 | High | Authorization / financial control | Direct PO approval route is broader than the approval decision authority. | `backend/app/routers/purchase.py:32,326-363` | Verified | High |
| VNT-003 | High | Authorization / financial control | Direct invoice approval route bypasses the approval queue and role authority. | `backend/app/routers/purchase.py:455-480` | Verified | High |
| VNT-004 | High | Concurrency | Budget approval is race-prone. | `backend/app/routers/purchase.py:326-363; backend/app/routers/catalog.py:60-100` | Verified | High |
| VNT-005 | High | Concurrency / inventory | Receipt cumulative quantity check is race-prone. | `backend/app/routers/purchase.py:383-416` | Verified | High |
| VNT-006 | High | Reliability / idempotency | Idempotency is replay-safe after completion but not atomic against concurrent duplicate requests. | `backend/app/core/idempotency.py:98-139` | Verified | High |
| VNT-007 | High | Security | Webhook endpoint validation does not provide SSRF protection. | `backend/app/routers/integrations.py:46-83; backend/app/services/integration.py:81-125` | Verified | High |
| VNT-008 | High | Integration reliability | Webhook delivery is synchronous and has no durable retry worker. | `backend/app/services/integration.py:74-133` | Verified | High |
| VNT-009 | High | Persistence | Uploaded documents default to container-local filesystem storage. | `backend/app/services/document.py:72-82; backend/app/routers/documents.py:80-85,144-159; docker-compose.yml:95-110` | Verified | High |
| VNT-010 | High | Upload reliability / security | Upload endpoint reads the entire file into memory before enforcing the configured size limit. | `backend/app/routers/documents.py:49-72` | Verified | High |
| VNT-011 | High | Document pipeline security | DOCX/XLSX ZIP parsing lacks archive bomb/resource limits. | `backend/app/services/extract.py:92-146` | Strong static finding | High |
| VNT-012 | Medium-High | Document validation | File type validation is based on a very small magic-byte sniff and extension conventions. | `backend/app/services/document.py:30-58; backend/app/routers/documents.py:60-71` | Verified | High |
| VNT-013 | Medium | Data integrity | Document attachment references are only length-validated, not target-validated. | `backend/app/routers/documents.py:86-104` | Verified | High |
| VNT-014 | Medium | AI safety | AI completion contract can return a factual-looking answer with an empty evidence list. | `backend/app/services/ai_gateway.py:247-271; backend/app/routers/ai.py:159-183; frontend/app/copilot/page.tsx:108-112` | Verified | High |
| VNT-015 | Medium | AI security | Caller-supplied system prompt is concatenated into the model system instruction without a fixed policy boundary. | `backend/app/routers/ai.py:159-172; backend/app/services/ai_gateway.py:247-271` | Verified | High |
| VNT-016 | Medium | Search / scalability | Document semantic search stores embeddings as JSON and performs application-side cosine ranking after ILIKE filtering. | `backend/app/models/document.py:36-48; backend/app/routers/documents.py:224-255; backend/app/services/embeddings.py:91-110` | Verified | High |
| VNT-017 | Medium | Notifications | Broadcast unread counts are intentionally capped and can be approximate at high volume. | `backend/app/routers/notifications.py:50-108` | Verified | High |
| VNT-018 | High | Workflow integrity | Critical lifecycle states are defined but not consistently reachable through first-class APIs. | `backend/app/models/purchase.py:20-23; backend/app/routers/purchase.py:206-480` | Verified | High |
| VNT-019 | Medium-High | Concurrency / sourcing | RFQ award has a concurrency window around the unique Award constraint. | `backend/app/routers/sourcing.py:260-323` | Verified | High |
| VNT-020 | Medium-High | Sourcing business logic | RFQ evaluation gate does not enforce quote completeness, minimum quote count, bid validity, or supplier eligibility. | `backend/app/routers/sourcing.py:160-180; 183-232` | Verified | High |
| VNT-021 | Medium | Sourcing / currency | Quote currency is not enforced to match the RFQ currency. | `backend/app/routers/sourcing.py:183-230; comparison at 235-257` | Verified | High |
| VNT-022 | High | Authorization / contracts | Contract status transitions and signing are authorized by broad write roles rather than specific authority. | `backend/app/routers/contracts.py:34,151-167,221-251` | Verified | High |
| VNT-023 | Medium-High | Contracts / e-sign | E-sign path records provider/envelope identifiers but does not verify external signature state. | `backend/app/routers/contracts.py:221-249` | Verified | High |
| VNT-024 | Medium | Operations / time | Contract expiry roll uses server date and is callable through a broad write endpoint. | `backend/app/routers/contracts.py:191-212` | Verified | High |
| VNT-025 | Medium-High | Supplier governance | Certification verification changes status without verifying the evidence itself or restricting verifier authority. | `backend/app/routers/suppliers.py:354-366` | Verified | High |
| VNT-026 | Medium | Supplier governance | Supplier qualification decision authority is broader than a specialized approval role. | `backend/app/routers/suppliers.py:410-433` | Verified | High |
| VNT-027 | Medium-High | Ledger integrity | Spend ledger uniqueness is enforced mainly by workflow state rather than database uniqueness. | `backend/app/models/spend.py and backend/app/routers/purchase.py:366-380,455-480` | Strong static finding | High |
| VNT-028 | Medium | Database integrity | Many important domain invariants are application-only and lack database-level defense-in-depth. | `backend/app/models/purchase.py, models/contract.py, models/document.py and migrations` | Strong static finding | High |
| VNT-029 | Medium | Performance | Synchronous HTTP/Redis work occurs inside async middleware paths. | `backend/app/core/security.py:46-61; backend/app/core/ratelimit.py:43-82` | Verified | High |
| VNT-030 | Medium | API hygiene | Client-provided request IDs are accepted without a strict format/length policy. | `backend/app/core/errors.py:22-28` | Verified | High |
| VNT-031 | Medium | Security headers | Content Security Policy is explicitly absent. | `backend/app/core/secheaders.py:1-23` | Verified | High |
| VNT-032 | Medium | Abuse prevention | Rate limiting is tenant-wide, method-wide, and fails open when Redis is unavailable. | `backend/app/core/ratelimit.py:43-82` | Verified | High |
| VNT-033 | Medium | Observability | Metrics are process-local and not suitable as the primary production telemetry system. | `backend/app/core/observe.py:22-47` | Verified | High |
| VNT-034 | High | Deployment security | Local Compose exposes sensitive infrastructure with development defaults and no production isolation. | `docker-compose.yml:1-110` | Verified | High |
| VNT-035 | Medium | Supply chain | Container dependencies use mutable tags instead of immutable image digests. | `docker-compose.yml:1-80` | Verified | High |
| VNT-036 | High | Identity / deployment | Keycloak realm/client/role bootstrap is not self-contained in the default Compose deployment. | `docker-compose.yml:63-80; .env.example around Keycloak variables` | Verified | High |
| VNT-037 | High | Frontend correctness | Copilot conversation turns reuse the IDs `you` and `ai`, causing duplicate React keys and incorrect updates across turns. | `frontend/app/copilot/page.tsx:59-80,153-155` | Verified | High |
| VNT-038 | Medium | Frontend UX flow | Provider options can say “needs your API key” but the Copilot page provides no key-entry flow. | `frontend/app/copilot/page.tsx:120-140` | Verified | High |
| VNT-039 | Medium | Frontend UI quality | The current UI implementation is a minimal admin-console design, not a polished enterprise procurement workspace. | `frontend/app/globals.css:103-220; frontend/components/ui.tsx:14-130; many page files` | Verified | High |
| VNT-040 | High | Testing / QA | Production-critical frontend and concurrency scenarios are not verified by the current automated suite. | `backend/tests; frontend package and CI configuration` | Verified | High |
| VNT-041 | Medium | Dashboard correctness | Dashboard expiry count depends on a stored status updated by a background roll, not a live calculation. | `frontend/app/page.tsx:121-124; backend/app/routers/contracts.py:191-212` | Verified | High |
| VNT-042 | Medium | Documentation | Repository documentation and actual test/route/version counts have drifted. | `README.md; backend/README.md; frontend/README.md; docs/00-plan/BUGS.md; actual source` | Verified | High |
| VNT-043 | Medium | Financial aggregation | Some summary values aggregate only under a single-currency assumption while the client has to suppress mixed-currency totals. | `backend/app/routers/spend.py; frontend/app/page.tsx:65-119` | Strong static finding | Medium |
| VNT-044 | Medium | Async jobs | Worker jobs depend on a manually provisioned service token and are not self-bootstrapping. | `worker/jobs.py:17-39; worker/beat.py:19-34; .env.example SERVICE_API_TOKEN` | Verified | High |
| VNT-045 | Medium | Frontend workflow | Key procurement actions are fragmented or missing dedicated operational surfaces in the current navigation. | `frontend/app route inventory; frontend/components/Shell.tsx; frontend/app/shared/orders.tsx and copilot approvals` | Verified | High |
