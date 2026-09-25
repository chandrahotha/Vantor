<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Domain Model — VANTOR

**Status: `PLANNED`. Full DDL lands in Phase 3 migrations.**

Core aggregates (all tenant-scoped via `tenant_id`/`org_id`):

- Identity: Organization, BusinessUnit, Department, User, Role, Permission (+ memberships, spending limits, approval authority).
- Supplier: Supplier, Contact, Address, Certification, Document, Risk, Scorecard, Performance.
- Catalog: Category, Product, Service.
- Sourcing: SourcingProject, Requirement, RFQ/RFP/RFI, RFQParticipant, RFQResponse, Quote, QuoteLine, QuoteEvaluation, Award.
- Contract: Contract, ContractVersion, Clause, Obligation, Risk, Renewal.
- P2P: PurchaseRequisition(+Lines), PurchaseOrder(+Lines), Receipt, Invoice(+Lines), SpendTransaction, SavingsOpportunity, SavingsRecord.
- Flow: Approval, ApprovalPolicy, ApprovalStep, Workflow, WorkflowInstance, WorkflowTask.
- Knowledge: Document, DocumentVersion, DocumentChunk, DocumentEmbedding (pgvector).
- AI: AIConversation, AIMessage, AITask, AIToolCall, AIEvidence (answer+confidence+evidence+timestamp+review flag).
- Platform: Notification, Integration, Webhook, AuditEvent (actor/tenant/action/resource/before/after/reason/approval/source).

Lifecycle states enumerated per aggregate (e.g., RFQ draft→sent→response→evaluated→awarded→closed; Contract draft→review→active→expiring→renewed/expired; PO draft→approved→sent→received→invoiced). Soft-delete only where audit/compliance demands; otherwise hard-delete with audit trail.
