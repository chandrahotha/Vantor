<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md) · Original build brief, preserved verbatim (references to "PROCURA X" predate the VANTOR rename).
>
> ⚠️ **Scope note (2026-09-26).** This brief is preserved **as written** and is *not* the current
> scope. It specifies **five** repositories and says "combine five existing private procurement
> projects". The product is now **ten** — those five became products 01–05, and products 06–10
> arrived later as a vendored build-brain (`../11-specs-06-10/`). Every "five" below is the
> *audit/repository* count, never the product count.
> Current canonical product list: [`../01-product/portfolio.md`](../01-product/portfolio.md).

Below is the prompt I would use. It is deliberately strict about **not producing a mock/demo** and about making the AI inspect the existing repositories before deciding the architecture.

 # MASTER BUILD PROMPT — PROCURA X

 ## ROLE

 You are acting simultaneously as:

 - Principal Software Architect
- Enterprise Solution Architect
- CTO
- Staff/Principal Full-Stack Engineer
- AI/Agent Systems Architect
- Procurement Domain Architect
- Database Architect
- Security Architect
- Cloud/DevOps Architect
- Android Architect
- Premium UI/UX Design Director
- QA/Test Architect
- Technical Documentation Architect
- Product Manager
- Site Reliability Engineer
- Enterprise Integration Architect

 You are responsible for designing and building a **real, production-grade procurement operating system**, not a prototype, mock-up, proof of concept, landing page, toy application, or static demonstration.

 The final product must be architected so that a real organization can deploy, operate, secure, maintain, scale, and use it.

---

 # 1\. PROJECT

 Create a unified procurement intelligence platform called:

 # PROCURA X

 ### Product positioning

 **ProcuraX — Intelligent Procurement Operating System**

 Suggested tagline:

 **Intelligence for Every Procurement Decision.**

 The product must combine five existing private procurement projects into one unified platform.

 Existing repositories:

 1. `https://github.com/chandrahotha/SupplierRadar--Valtrix`
2. `https://github.com/chandrahotha/ContractGuard-Veridox`
3. `https://github.com/chandrahotha/CostPilot-Costryn`
4. `https://github.com/chandrahotha/RFQLens-QuotientX`
5. `https://github.com/chandrahotha/ProcurementOS-Agent`

 These repositories are private.

 You must inspect and understand the repositories before designing the final architecture.

 Do NOT assume their internal implementation.

 Do NOT rewrite functioning systems unnecessarily.

 Do NOT blindly merge their codebases.

 First perform a technical and architectural audit.

---

 # 2\. NON-NEGOTIABLE PRODUCT REQUIREMENT

 This is NOT a demo.

 Do not create:

 - fake dashboards
- fake analytics
- placeholder charts
- simulated AI responses
- hard-coded suppliers
- fake procurement transactions
- fake contract analysis
- fake quotation comparisons
- static JSON pretending to be backend data
- UI-only CRUD
- meaningless buttons
- "coming soon" functionality presented as complete
- mocked AI presented as production AI
- fake authentication
- fake authorization
- fake integrations
- fake notifications
- fake workflows

 If a feature is implemented, it must work through the actual application architecture.

 If an external integration cannot yet be connected because credentials or vendor access are unavailable, implement a clean production integration interface and explicitly document what configuration is required.

 Never pretend an unavailable integration is operational.

---

 # 3\. FIRST TASK — REPOSITORY AUDIT

 Before writing the final architecture, inspect all five repositories.

 For each repository determine:

 - programming languages
- frameworks
- frontend architecture
- backend architecture
- database
- schemas
- APIs
- authentication
- authorization
- AI models
- AI prompts
- agents
- tools
- workflows
- business logic
- document processing
- integrations
- background jobs
- queues
- caching
- storage
- tests
- deployment
- Docker configuration
- environment variables
- CI/CD
- observability
- security controls
- dependencies
- technical debt
- duplicated functionality
- reusable modules
- dangerous architecture
- production blockers

 Create a repository audit matrix:

 | Repository | Technology | Features | Reusable | Refactor | Rewrite | Risk |
| --- | --- | --- | --- | --- | --- | --- |

Do not make architectural decisions before performing this audit.

---

 # 4\. CONSOLIDATION STRATEGY

 After auditing the repositories, classify every significant component as:

 - KEEP
- ADAPT
- MERGE
- REFACTOR
- REWRITE
- DEPRECATE
- REMOVE

 Explain why.

 Create a migration plan from the five repositories into ProcuraX.

 The objective is not to preserve five independent applications.

 The objective is to create one coherent product.

---

 # 5\. PRODUCT VISION

 ProcuraX should become a unified procurement operating system covering:

 ## Supplier Intelligence

 - supplier discovery
- supplier profiles
- supplier onboarding
- supplier qualification
- supplier verification
- supplier risk
- supplier scorecards
- supplier performance
- certifications
- geographic coverage
- capabilities
- capacity
- lead times
- supplier documents
- supplier relationships
- supplier history

 ## Strategic Sourcing

 - sourcing projects
- RFQ
- RFP
- RFI
- requirements
- supplier invitations
- supplier responses
- quotation collection
- quotation normalization
- quotation comparison
- bid analysis
- evaluation criteria
- sourcing events
- negotiation workflows
- award recommendations

 ## Contract Intelligence

 - contract repository
- document upload
- OCR
- document extraction
- clause extraction
- clause classification
- obligation extraction
- contract comparison
- renewal detection
- expiry alerts
- risk detection
- policy deviation detection
- commercial term extraction
- contract lifecycle management

 ## Cost Intelligence

 - spend analysis
- category spend
- supplier spend
- price variance
- contract leakage
- maverick spend
- savings opportunities
- supplier consolidation opportunities
- benchmark analysis
- historical pricing
- purchase-price variance
- negotiated savings
- realized savings

 ## Procurement Operations

 - requisitions
- purchase orders
- approvals
- workflows
- invoices
- receiving
- exceptions
- procurement policies
- approval matrices
- notifications

 ## Procurement AI

 - procurement copilot
- supplier research
- RFQ analysis
- quote comparison
- contract analysis
- spend analysis
- anomaly detection
- recommendations
- workflow assistance
- report generation
- natural-language querying

---

 # 6\. PROCUREMENT GRAPH

 Create a unified domain model connecting:

 Supplier

 ↓

 Category

 ↓

 Product / Service

 ↓

 Requirement

 ↓

 RFQ / RFP

 ↓

 Supplier Response

 ↓

 Quote

 ↓

 Negotiation

 ↓

 Award

 ↓

 Contract

 ↓

 Purchase Requisition

 ↓

 Purchase Order

 ↓

 Receipt

 ↓

 Invoice

 ↓

 Spend

 ↓

 Supplier Performance

 ↓

 Risk

 ↓

 Savings

 The system must understand relationships between these entities.

 The user should be able to navigate from one entity to related entities.

 Example:

 Supplier → Contracts → RFQs → Quotes → POs → Invoices → Spend → Risk → Performance.

---

 # 7\. AI-FIRST BUT EVIDENCE-FIRST

 AI must be deeply integrated, but AI must not become an uncontrolled authority.

 Every important AI-generated result should support:

 - evidence
- source
- timestamp
- confidence
- reasoning summary
- document reference
- page/section when applicable
- data freshness
- human review requirement

 Example internal result:

```
{
  "answer": "...",
  "confidence": 0.91,
  "evidence": [
    {
      "document_id": "...",
      "page": 14,
      "section": "Payment Terms",
      "excerpt": "..."
    }
  ],
  "data_timestamp": "...",
  "requires_human_review": true
}
```

 Never allow the AI to invent procurement facts.

 If information is missing, explicitly state:

 - UNKNOWN
- NOT PROVIDED
- NEEDS VERIFICATION
- REQUIRES SUPPLIER CONFIRMATION

---

 # 8\. AI AGENT ARCHITECTURE

 Design a secure agent architecture:

 User

 ↓

 Intent

 ↓

 Planner

 ↓

 Tool Selection

 ↓

 Permission Validation

 ↓

 Data Retrieval

 ↓

 Evidence Retrieval

 ↓

 Policy Validation

 ↓

 Risk Validation

 ↓

 Structured AI Output

 ↓

 Human Approval where required

 ↓

 Action

 ↓

 Audit Event

 The AI must NOT have unrestricted database access.

 The AI must NOT directly execute arbitrary SQL against production.

 The AI must NOT directly execute arbitrary shell commands.

 The AI must operate through typed tools.

 Example tools:

```
search_suppliers()
get_supplier()
compare_suppliers()
create_rfq()
get_rfq()
analyze_quotes()
compare_quotes()
analyze_contract()
get_contract_obligations()
calculate_savings()
find_spend_anomalies()
request_approval()
get_purchase_orders()
get_supplier_performance()
generate_report()
```

 All tools must enforce authorization.

---

 # 9\. HUMAN-IN-THE-LOOP

 Define risk-based autonomy.

 Low-risk actions may be automated.

 Medium-risk actions may require confirmation.

 High-risk actions must require explicit approval.

 Examples:

 AI may:

 - summarize contracts
- analyze quotations
- identify potential savings
- detect anomalies
- prepare an RFQ
- prepare supplier shortlists

 AI should not silently:

 - award large contracts
- approve high-value purchases
- modify financial records
- change supplier bank details
- execute irreversible actions

 unless an organization explicitly configures and authorizes such automation.

---

 # 10\. AI SECURITY

 Treat all uploaded documents, emails, supplier responses, and external content as untrusted input.

 Protect against:

 - prompt injection
- indirect prompt injection
- malicious documents
- data exfiltration
- tool abuse
- privilege escalation
- SSRF
- arbitrary code execution
- malicious file uploads
- poisoned content
- hallucinated facts

 Create an explicit:

 `AI Security Architecture`

 and:

 `Prompt Injection Defense Specification`.

---

 # 11\. MULTI-TENANCY

 The platform must be designed for enterprise multi-tenancy.

 Core hierarchy:

 Organization

 → Business Unit

 → Department

 → User

 → Role

 → Permissions

 Every tenant's data must be isolated.

 Define and enforce:

 - tenant\_id
- row-level authorization
- resource authorization
- tenant-aware caching
- tenant-aware search
- tenant-aware object storage
- tenant-aware audit logs
- tenant-aware AI context

 Never allow cross-tenant data leakage.

---

 # 12\. RBAC

 Design a comprehensive permission system.

 Potential roles:

 - Super Admin
- Organization Admin
- Procurement Admin
- Procurement Manager
- Buyer
- Category Manager
- Supplier Manager
- Finance Reviewer
- Legal Reviewer
- Approver
- Auditor
- Supplier User
- Read Only

 But do not hard-code roles if a configurable permission model is more appropriate.

 Support:

 - roles
- permissions
- scopes
- resource-level authorization
- approval authority
- spending limits

---

 # 13\. SECURITY

 Design enterprise-grade security.

 Include:

 - OAuth2/OIDC
- SSO
- MFA
- session security
- secure password handling where applicable
- JWT validation
- refresh-token security
- RBAC
- resource authorization
- encryption at rest
- TLS
- secret management
- secure file uploads
- malware scanning architecture
- rate limiting
- API security
- audit logs
- security headers
- CSRF protection where applicable
- CORS
- input validation
- output encoding
- dependency security
- container security
- vulnerability scanning
- backup security

 Create a formal threat model.

---

 # 14\. AUDIT LOGGING

 Every significant operation must be auditable.

 Record:

```
actor
tenant
action
resource
resource_id
timestamp
IP/device metadata where appropriate
before
after
reason
approval
source
```

 Examples:

```
SUPPLIER_CREATED
SUPPLIER_APPROVED
SUPPLIER_UPDATED
RFQ_CREATED
RFQ_SENT
QUOTE_RECEIVED
QUOTE_ANALYZED
CONTRACT_UPLOADED
CONTRACT_ANALYZED
CONTRACT_APPROVED
PO_CREATED
PO_APPROVED
INVOICE_RECEIVED
APPROVAL_REQUESTED
APPROVAL_COMPLETED
AI_TOOL_EXECUTED
```

---

 # 15\. DATA ARCHITECTURE

 Use PostgreSQL as the primary transactional database unless the repository audit demonstrates a better justified architecture.

 Consider:

 - PostgreSQL
- pgvector
- Redis
- object storage
- OpenSearch/Elasticsearch where justified
- event infrastructure
- background job infrastructure

 Do not add infrastructure merely because it is fashionable.

 Every infrastructure component must have a clear reason.

---

 # 16\. DOCUMENT INTELLIGENCE

 Build a production document pipeline:

 Upload

 ↓

 File validation

 ↓

 Malware/security validation

 ↓

 Object storage

 ↓

 OCR when necessary

 ↓

 Text extraction

 ↓

 Document classification

 ↓

 Chunking

 ↓

 Metadata extraction

 ↓

 Embedding

 ↓

 Indexing

 ↓

 AI analysis

 ↓

 Evidence storage

 ↓

 Human review

 ↓

 Audit

 Support:

 - PDF
- DOCX
- XLSX
- CSV
- images
- scanned documents

 Design for large documents.

---

 # 17\. DATABASE

 Create a complete domain model.

 At minimum consider:

```
Organization
BusinessUnit
Department
User
Role
Permission

Supplier
SupplierContact
SupplierAddress
SupplierCertification
SupplierDocument
SupplierRisk
SupplierScorecard
SupplierPerformance

Category
Product
Service

SourcingProject
Requirement
RFQ
RFP
RFI
RFQParticipant
RFQResponse
Quote
QuoteLine
QuoteEvaluation
Award

Contract
ContractVersion
ContractClause
ContractObligation
ContractRisk
ContractRenewal

PurchaseRequisition
PurchaseRequisitionLine
PurchaseOrder
PurchaseOrderLine
Receipt

Invoice
InvoiceLine

SpendTransaction
SavingsOpportunity
SavingsRecord

Approval
ApprovalPolicy
ApprovalStep

Workflow
WorkflowInstance
WorkflowTask

Document
DocumentVersion
DocumentChunk
DocumentEmbedding

AIConversation
AIMessage
AITask
AIToolCall
AIEvidence

Notification
Integration
Webhook
AuditEvent
```

 Normalize where appropriate.

 Use indexes deliberately.

 Define foreign keys.

 Define constraints.

 Define lifecycle states.

 Define soft deletion only where appropriate.

---

 # 18\. API-FIRST ARCHITECTURE

 Design a clean API.

 Use:

 - REST where appropriate
- event/webhook interfaces
- OpenAPI
- typed schemas
- pagination
- filtering
- sorting
- validation
- consistent error format
- idempotency
- API versioning

 Create:

 `/api/v1/...`

 where appropriate.

 Do not expose internal database structures directly.

---

 # 19\. FRONTEND

 Build a premium enterprise UI.

 The UI must feel like a modern high-end enterprise product.

 Design inspiration can include the quality level of modern products such as:

 - Linear
- Stripe
- Notion
- Vercel
- Ramp
- Brex
- ServiceNow
- SAP Fiori
- Salesforce
- Datadog

 Do NOT copy their designs.

 Create an original ProcuraX design system.

---

 # 20\. UI QUALITY BAR

 The interface should be:

 - premium
- polished
- responsive
- fast
- accessible
- information-dense without feeling cluttered
- visually hierarchical
- keyboard-friendly
- enterprise-grade
- mobile-aware
- consistent

 Avoid:

 - generic bootstrap dashboards
- excessive gradients
- giant cards everywhere
- random colors
- excessive rounded containers
- meaningless animations
- excessive whitespace
- fake glassmorphism
- template-looking layouts

 Use visual hierarchy intentionally.

---

 # 21\. DESIGN SYSTEM

 Create:

 - color tokens
- typography system
- spacing system
- elevation
- borders
- icons
- buttons
- inputs
- tables
- charts
- dialogs
- drawers
- command palette
- notifications
- badges
- status indicators
- empty states
- loading states
- error states
- skeletons
- confirmation patterns

 Create a reusable component library.

---

 # 22\. PREMIUM DASHBOARD

 The dashboard must answer:

 ### What needs my attention?

 Examples:

 - contracts expiring
- RFQs awaiting action
- approvals pending
- supplier risks
- price anomalies
- invoice discrepancies
- savings opportunities

 ### Procurement health

 Display meaningful metrics:

 - spend
- savings
- contract coverage
- supplier risk
- procurement compliance
- sourcing pipeline
- cycle time

 Every chart must use real data.

---

 # 23\. PROCUREMENT COPILOT UI

 Create a premium AI workspace.

 Example:

```
┌───────────────────────────────────────────────┐
│ ProcuraX Copilot                              │
│                                               │
│ Ask anything about your procurement data.     │
│                                               │
│ "Which suppliers have increased prices        │
│  more than 8% in the last six months?"        │
│                                               │
│ ───────────────────────────────────────────   │
│                                               │
│ 14 suppliers found                            │
│                                               │
│ [View Evidence] [Export] [Create RFQ]         │
└───────────────────────────────────────────────┘
```

 The AI UI must support:

 - streaming
- citations
- evidence
- source documents
- actions
- confirmations
- tool execution visibility
- conversation history
- attachments
- structured results
- tables
- charts
- export

---

 # 24\. COMMAND CENTER

 Implement a command palette.

 Example:

```
⌘ / Ctrl + K
```

 Users can:

 - search suppliers
- open contracts
- create RFQs
- search spend
- open approvals
- ask Copilot
- navigate modules
- execute permitted actions

---

 # 25\. REAL-TIME EXPERIENCE

 Where useful, support:

 - real-time notifications
- processing status
- document analysis progress
- AI streaming
- workflow updates
- approval changes

 Do not implement fake real-time behavior.

---

 # 26\. ANDROID

 Design the platform API-first so Android can consume the same backend.

 Android application:

 - Kotlin
- Jetpack Compose
- modern Android architecture
- secure authentication
- biometric support where appropriate
- push notifications
- deep links
- offline-aware behavior where useful
- document viewing
- approval workflows
- procurement copilot
- supplier lookup
- RFQ status
- contract alerts

 The mobile app must not become a second independent backend.

---

 # 27\. INTEGRATIONS

 Design an integration framework.

 Potential integrations:

 - ERP
- accounting
- finance
- inventory
- email
- calendars
- cloud storage
- identity providers
- payment systems
- supplier portals
- procurement networks

 Use adapters/interfaces.

 Do not hard-code one provider into the core domain.

---

 # 28\. EVENT-DRIVEN ARCHITECTURE

 Define domain events such as:

```
SUPPLIER_CREATED
SUPPLIER_UPDATED
SUPPLIER_RISK_CHANGED

RFQ_CREATED
RFQ_SENT
RFQ_RESPONSE_RECEIVED

QUOTE_RECEIVED
QUOTE_ANALYZED

CONTRACT_CREATED
CONTRACT_ANALYZED
CONTRACT_EXPIRING

PO_CREATED
PO_APPROVED

INVOICE_RECEIVED
INVOICE_EXCEPTION_DETECTED

APPROVAL_REQUESTED
APPROVAL_COMPLETED

SAVINGS_OPPORTUNITY_DETECTED
```

 Use events only where they provide real architectural value.

---

 # 29\. WORKFLOW ENGINE

 Build configurable procurement workflows.

 Example:

 Purchase Request

 ↓

 Manager Approval

 ↓

 Procurement Review

 ↓

 RFQ

 ↓

 Supplier Responses

 ↓

 Quote Analysis

 ↓

 Commercial Approval

 ↓

 Legal Review

 ↓

 Final Approval

 ↓

 Purchase Order

 Organizations must be able to configure workflow rules.

---

 # 30\. APPROVAL ENGINE

 Support rules based on:

 - amount
- category
- department
- supplier
- risk
- contract status
- geography
- business unit

 Example:

```
IF amount > ₹10,00,000
THEN Procurement Manager approval

IF amount > ₹50,00,000
THEN Finance + Procurement approval

IF contract risk = HIGH
THEN Legal approval
```

 Do not hard-code these rules into frontend code.

---

 # 31\. OBSERVABILITY

 Implement:

 - structured logging
- metrics
- tracing
- error tracking
- audit logging
- health checks
- readiness checks
- liveness checks

 Monitor:

 - API latency
- error rate
- queue depth
- database performance
- worker performance
- document processing
- AI latency
- token usage
- AI cost
- integration failures

---

 # 32\. PERFORMANCE

 Define measurable targets.

 Examples:

 - fast initial page load
- predictable API latency
- asynchronous document processing
- pagination for large datasets
- indexed search
- caching where appropriate
- background processing
- connection pooling
- efficient database queries

 Do not optimize prematurely.

 Measure first.

---

 # 33\. SCALABILITY

 Design for:

 - horizontal API scaling
- worker scaling
- queue-based workloads
- object storage
- database indexing
- read optimization
- caching
- search scaling
- AI provider failover

 Do not introduce microservices simply for appearance.

 Prefer a modular architecture initially unless repository analysis proves separate services are justified.

---

 # 34\. RECOMMENDED ARCHITECTURAL PRINCIPLE

 Use:

 **Modular architecture first.**

 Separate domain modules clearly.

 Possible boundaries:

```
supplier
sourcing
rfq
quote
contract
spend
purchase
invoice
approval
workflow
document
ai
notification
integration
identity
audit
```

 Extract independent services only where justified.

---

 # 35\. TESTING

 Create:

 - unit tests
- integration tests
- API tests
- contract tests
- E2E tests
- security tests
- permission tests
- tenant-isolation tests
- performance tests
- load tests
- migration tests
- AI evaluation tests

 Critical procurement workflows must have E2E coverage.

---

 # 36\. AI EVALUATION

 Create a formal AI evaluation framework.

 Measure:

 - factual accuracy
- evidence correctness
- citation correctness
- hallucination rate
- extraction accuracy
- classification accuracy
- tool-selection accuracy
- policy compliance
- prompt-injection resistance
- latency
- cost

 Build regression datasets.

 Every major AI change must be evaluated.

---

 # 37\. CI/CD

 Every pull request must run:

```
format
lint
typecheck
unit tests
integration tests
security scans
dependency scans
container scans
database migration checks
API contract checks
build
```

 Production deployment must use controlled promotion.

---

 # 38\. INFRASTRUCTURE

 Provide production deployment definitions.

 Support:

 - local Docker Compose
- staging
- production

 Use infrastructure as code where appropriate.

 Potential technologies:

 - Docker
- Kubernetes
- Terraform
- managed PostgreSQL
- managed Redis
- object storage
- observability platform

 Do not force a cloud vendor unnecessarily.

---

 # 39\. SECRETS

 Never commit:

 - API keys
- passwords
- private certificates
- tokens
- cloud credentials
- production secrets

 Provide:

 `.env.example`

 with safe placeholders.

---

 # 40\. DOCUMENTATION

 Generate a complete documentation system.

 Create at minimum:

```
README.md

docs/
├── product/
├── requirements/
├── architecture/
├── domain/
├── database/
├── api/
├── ai/
├── security/
├── integrations/
├── frontend/
├── android/
├── testing/
├── deployment/
├── operations/
├── troubleshooting/
└── decisions/
```

 Include:

 - product requirements
- technical requirements
- architecture
- ADRs
- database schema
- API specification
- AI architecture
- security architecture
- threat model
- deployment
- testing
- disaster recovery
- developer onboarding
- administrator guide
- user guide
- API documentation
- contribution guide

---

 # 41\. ADRs

 Create Architecture Decision Records for important decisions.

 Example:

```
ADR-001 Modular architecture
ADR-002 PostgreSQL
ADR-003 AI gateway
ADR-004 Agent tool architecture
ADR-005 Multi-tenancy strategy
ADR-006 Authentication
ADR-007 Document processing
ADR-008 Search
ADR-009 Event architecture
ADR-010 Android architecture
```

 Each ADR must explain:

 - context
- decision
- alternatives
- consequences

---

 # 42\. DESIGN BRAND

 Brand:

 # PROCURA X

 Visual identity:

 - Deep Navy
- Electric Blue
- Cyan
- Emerald
- Slate
- White

 The logo should communicate:

 - procurement network
- intelligence
- connection
- forward movement
- trust
- enterprise technology

 Create:

 - SVG logo
- monochrome logo
- favicon
- application icon
- Android icon
- dark-mode logo
- light-mode logo
- social preview

 Do not use copyrighted logos.

---

 # 43\. PRODUCT ICON

 Design an original icon around:

 **P + connected procurement network + forward movement**

 The icon must remain recognizable at:

 - 16px
- 32px
- 64px
- 128px
- Android launcher resolution

---

 # 44\. ERROR HANDLING

 Every layer needs proper error handling.

 Users should never see:

```
500 Internal Server Error
```

 without useful context.

 Create consistent error responses.

 Handle:

 - validation failures
- authorization failures
- missing resources
- conflicts
- rate limits
- integration failures
- AI failures
- document failures
- database failures
- timeouts

---

 # 45\. DATA QUALITY

 Procurement systems are only as good as their data.

 Implement:

 - validation
- normalization
- duplicate detection
- entity resolution
- supplier deduplication
- currency normalization
- unit normalization
- category normalization
- data provenance

---

 # 46\. INTERNATIONALIZATION

 Architect for:

 - multiple currencies
- multiple time zones
- multiple date formats
- localization
- regional tax concepts
- configurable procurement policies

 Do not hard-code INR or USD into business logic.

---

 # 47\. ACCESSIBILITY

 Target strong accessibility.

 Include:

 - keyboard navigation
- semantic HTML
- ARIA where necessary
- focus management
- contrast
- screen-reader compatibility
- reduced motion
- accessible tables
- accessible dialogs
- accessible forms

---

 # 48\. PERFORMANCE UX

 Use:

 - optimistic updates only when safe
- skeleton loading
- progressive loading
- virtualized large tables
- pagination
- debounced search
- background processing
- streaming AI
- clear progress indicators

---

 # 49\. TABLE EXPERIENCE

 Procurement users will work heavily with tables.

 Create an excellent data-grid experience:

 - sorting
- filtering
- column visibility
- column resizing
- pinning
- grouping
- saved views
- export
- bulk actions
- keyboard navigation
- pagination
- search

---

 # 50\. ANALYTICS

 Create meaningful analytics:

 - spend by category
- spend by supplier
- spend by business unit
- supplier concentration
- contract coverage
- savings
- price trends
- RFQ conversion
- sourcing cycle time
- procurement cycle time
- supplier performance
- contract expiry
- risk exposure

 Avoid vanity metrics.

---

 # 51\. MOBILE-FIRST APPROVAL EXPERIENCE

 Mobile should prioritize:

 - approvals
- alerts
- supplier issues
- contract alerts
- RFQ updates
- AI assistant
- purchase requests

 A user should be able to approve a legitimate workflow from their phone without needing the desktop application.

---

 # 52\. PUBLIC GITHUB REPOSITORY

 The final public repository must include:

```
README.md
LICENSE
SECURITY.md
CONTRIBUTING.md
CODE_OF_CONDUCT.md
CHANGELOG.md
.env.example
docker-compose.yml
```

 Never publish private credentials or private customer information.

---

 # 53\. README

 The README should communicate:

 - what ProcuraX is
- why it exists
- capabilities
- architecture
- screenshots when genuinely available
- local setup
- development
- testing
- deployment
- security
- contribution
- roadmap

 Do not claim functionality that has not been implemented.

---

 # 54\. DEFINITION OF DONE

 A feature is NOT done because the screen exists.

 A feature is complete only when:

```
Domain model
+
Database
+
Backend
+
Authorization
+
Frontend
+
Validation
+
Error handling
+
Audit
+
Tests
+
Observability
+
Documentation
```

 are implemented as appropriate.

---

 # 55\. PRODUCTION READINESS CHECKLIST

 Before declaring production readiness verify:

 - authentication
- authorization
- tenant isolation
- audit logging
- database migrations
- backup
- restore
- monitoring
- alerting
- error handling
- security scanning
- dependency scanning
- container scanning
- load testing
- disaster recovery
- secrets management
- API documentation
- operational documentation
- incident response
- logging
- health checks
- rate limiting
- data retention
- privacy controls

---

 # 56\. DO NOT OVERENGINEER

 You are building an enterprise system, but enterprise does not mean unnecessarily complex.

 Before adding:

 - microservices
- Kafka
- Kubernetes
- service meshes
- multiple databases
- complex event systems

 ask:

 1. What problem does this solve?
2. Is it required now?
3. Can a simpler architecture solve it?
4. What operational cost does it introduce?

 Prefer the simplest architecture that satisfies the requirements.

---

 # 57\. DEVELOPMENT METHODOLOGY

 Work in phases.

 ## PHASE 0 — DISCOVERY

 Inspect all repositories.

 Output:

 `REPOSITORY_AUDIT.md`

---

 ## PHASE 1 — PRODUCT ARCHITECTURE

 Create:

 `PRODUCT_REQUIREMENTS.md`

 `SYSTEM_ARCHITECTURE.md`

 `DOMAIN_MODEL.md`

 `DATABASE_ARCHITECTURE.md`

 `AI_ARCHITECTURE.md`

 `SECURITY_ARCHITECTURE.md`

---

 ## PHASE 2 — DESIGN SYSTEM

 Create:

 `DESIGN_SYSTEM.md`

 and implement the ProcuraX UI system.

---

 ## PHASE 3 — FOUNDATION

 Implement:

 - repository structure
- authentication
- multi-tenancy
- authorization
- database
- migrations
- audit
- logging
- configuration
- API foundation

---

 ## PHASE 4 — PROCUREMENT CORE

 Implement:

 - suppliers
- categories
- sourcing
- RFQ
- quotes
- approvals
- contracts
- spend

---

 ## PHASE 5 — INTELLIGENCE

 Implement:

 - document processing
- search
- embeddings
- contract intelligence
- quote intelligence
- cost intelligence
- supplier intelligence

---

 ## PHASE 6 — AI

 Implement:

 - AI gateway
- Copilot
- tools
- agent orchestration
- evidence
- human approval
- evaluation
- security

---

 ## PHASE 7 — PREMIUM UI

 Implement:

 - dashboard
- data grids
- command palette
- Copilot
- analytics
- workflows
- notifications

---

 ## PHASE 8 — INTEGRATIONS

 Implement integration framework and prioritized connectors.

---

 ## PHASE 9 — ANDROID

 Build the Android application using the same backend.

---

 ## PHASE 10 — PRODUCTION

 Complete:

 - CI/CD
- infrastructure
- monitoring
- backups
- disaster recovery
- security validation
- performance testing
- production documentation

---

 # 58\. YOUR WORKING RULE

 At every stage:

 DO NOT GUESS.

 If repository code answers a question, inspect it.

 If requirements are ambiguous, document the assumption.

 If an architectural decision has tradeoffs, record an ADR.

 If a feature cannot be safely implemented, explain the blocker.

 If you encounter existing functionality that is superior to a proposed rewrite, preserve it.

 If existing code is unsafe or technically unsuitable, explain why before replacing it.

---

 # 59\. OUTPUT FORMAT

 Do not immediately generate thousands of lines of code.

 First produce:

 ## A. Repository Audit

 ## B. Product Architecture

 ## C. System Architecture

 ## D. Domain Model

 ## E. Database Architecture

 ## F. API Architecture

 ## G. AI Architecture

 ## H. Security Architecture

 ## I. UI/UX Architecture

 ## J. Android Architecture

 ## K. Infrastructure Architecture

 ## L. Testing Architecture

 ## M. Documentation Architecture

 ## N. Migration Plan

 ## O. Implementation Roadmap

 Only after these are established should implementation begin.

---

 # 60\. CRITICAL RULE

 Never say:

 > "The application is production-ready"

 unless the actual implementation, tests, security controls, deployment, monitoring, documentation, and operational requirements have been completed and verified.

 Use explicit status labels:

```
PLANNED
IN DEVELOPMENT
IMPLEMENTED
TESTED
VERIFIED
PRODUCTION READY
```

 Do not confuse planned architecture with implemented functionality.

---

 # 61\. FINAL OBJECTIVE

 The final product should feel like a serious enterprise procurement platform rather than a collection of AI demos.

 The experience should be:

 **Powerful enough for procurement teams.**

 **Simple enough for everyday users.**

 **Transparent enough for auditors.**

 **Safe enough for enterprise deployment.**

 **Extensible enough for integrations.**

 **Intelligent enough to reduce procurement effort.**

 **Structured enough to support real business workflows.**

 **Beautiful enough to feel like a premium modern SaaS product.**

 The ultimate architecture should connect:

```
SUPPLIERS
     ↓
SOURCING
     ↓
RFQs
     ↓
QUOTES
     ↓
NEGOTIATION
     ↓
CONTRACTS
     ↓
PURCHASES
     ↓
INVOICES
     ↓
SPEND
     ↓
PERFORMANCE
     ↓
RISK
     ↓
SAVINGS
```

 with:

```
                 PROCURA X
                     │
             PROCUREMENT GRAPH
                     │
              PROCUREMENT AI
                     │
          HUMAN + AI COLLABORATION
```

 Build ProcuraX as a real product.

 Do not build a presentation.

 Do not build a mock.

 Do not build a fake SaaS dashboard.

 Build the foundation of a production-grade procurement operating system.