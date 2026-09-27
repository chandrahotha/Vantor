<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Verified Evidence Index

- **VNT-001** — `backend/app/services/purchase.py:123-153 (`three_way_match`); backend/app/routers/purchase.py:455-480 (`approve_invoice`)` — Verified — High
- **VNT-002** — `backend/app/routers/purchase.py:32,326-363` — Verified — High
- **VNT-003** — `backend/app/routers/purchase.py:455-480` — Verified — High
- **VNT-004** — `backend/app/routers/purchase.py:326-363; backend/app/routers/catalog.py:60-100` — Verified — High
- **VNT-005** — `backend/app/routers/purchase.py:383-416` — Verified — High
- **VNT-006** — `backend/app/core/idempotency.py:98-139` — Verified — High
- **VNT-007** — `backend/app/routers/integrations.py:46-83; backend/app/services/integration.py:81-125` — Verified — High
- **VNT-008** — `backend/app/services/integration.py:74-133` — Verified — High
- **VNT-009** — `backend/app/services/document.py:72-82; backend/app/routers/documents.py:80-85,144-159; docker-compose.yml:95-110` — Verified — High
- **VNT-010** — `backend/app/routers/documents.py:49-72` — Verified — High
- **VNT-011** — `backend/app/services/extract.py:92-146` — Strong static finding — High
- **VNT-012** — `backend/app/services/document.py:30-58; backend/app/routers/documents.py:60-71` — Verified — High
- **VNT-013** — `backend/app/routers/documents.py:86-104` — Verified — High
- **VNT-014** — `backend/app/services/ai_gateway.py:247-271; backend/app/routers/ai.py:159-183; frontend/app/copilot/page.tsx:108-112` — Verified — High
- **VNT-015** — `backend/app/routers/ai.py:159-172; backend/app/services/ai_gateway.py:247-271` — Verified — High
- **VNT-016** — `backend/app/models/document.py:36-48; backend/app/routers/documents.py:224-255; backend/app/services/embeddings.py:91-110` — Verified — High
- **VNT-017** — `backend/app/routers/notifications.py:50-108` — Verified — High
- **VNT-018** — `backend/app/models/purchase.py:20-23; backend/app/routers/purchase.py:206-480` — Verified — High
- **VNT-019** — `backend/app/routers/sourcing.py:260-323` — Verified — High
- **VNT-020** — `backend/app/routers/sourcing.py:160-180; 183-232` — Verified — High
- **VNT-021** — `backend/app/routers/sourcing.py:183-230; comparison at 235-257` — Verified — High
- **VNT-022** — `backend/app/routers/contracts.py:34,151-167,221-251` — Verified — High
- **VNT-023** — `backend/app/routers/contracts.py:221-249` — Verified — High
- **VNT-024** — `backend/app/routers/contracts.py:191-212` — Verified — High
- **VNT-025** — `backend/app/routers/suppliers.py:354-366` — Verified — High
- **VNT-026** — `backend/app/routers/suppliers.py:410-433` — Verified — High
- **VNT-027** — `backend/app/models/spend.py and backend/app/routers/purchase.py:366-380,455-480` — Strong static finding — High
- **VNT-028** — `backend/app/models/purchase.py, models/contract.py, models/document.py and migrations` — Strong static finding — High
- **VNT-029** — `backend/app/core/security.py:46-61; backend/app/core/ratelimit.py:43-82` — Verified — High
- **VNT-030** — `backend/app/core/errors.py:22-28` — Verified — High
- **VNT-031** — `backend/app/core/secheaders.py:1-23` — Verified — High
- **VNT-032** — `backend/app/core/ratelimit.py:43-82` — Verified — High
- **VNT-033** — `backend/app/core/observe.py:22-47` — Verified — High
- **VNT-034** — `docker-compose.yml:1-110` — Verified — High
- **VNT-035** — `docker-compose.yml:1-80` — Verified — High
- **VNT-036** — `docker-compose.yml:63-80; .env.example around Keycloak variables` — Verified — High
- **VNT-037** — `frontend/app/copilot/page.tsx:59-80,153-155` — Verified — High
- **VNT-038** — `frontend/app/copilot/page.tsx:120-140` — Verified — High
- **VNT-039** — `frontend/app/globals.css:103-220; frontend/components/ui.tsx:14-130; many page files` — Verified — High
- **VNT-040** — `backend/tests; frontend package and CI configuration` — Verified — High
- **VNT-041** — `frontend/app/page.tsx:121-124; backend/app/routers/contracts.py:191-212` — Verified — High
- **VNT-042** — `README.md; backend/README.md; frontend/README.md; docs/00-plan/BUGS.md; actual source` — Verified — High
- **VNT-043** — `backend/app/routers/spend.py; frontend/app/page.tsx:65-119` — Strong static finding — Medium
- **VNT-044** — `worker/jobs.py:17-39; worker/beat.py:19-34; .env.example SERVICE_API_TOKEN` — Verified — High
- **VNT-045** — `frontend/app route inventory; frontend/components/Shell.tsx; frontend/app/shared/orders.tsx and copilot approvals` — Verified — High
