# Domain Model

Tenant
User
Role
Workspace
Supplier
SupplierSite
Item
Category
Commodity
Contract
ContractClause
RFQ
RFQLine
SupplierQuote
SupplierQuoteLine
PriceHistory
CostModel
CostElement
SourcingScenario
ScenarioAllocation
RiskSignal
SupplierMetric
ComplianceRule
RuleSet
Document
DocumentVersion
ExtractionField
EvidenceSpan
AIJob
AIResult
Approval
Notification
Report
ExportJob
Integration
AuditEvent

Money:
use integer minor units or Decimal + ISO 4217. Never float. Every conversion stores FX source/time.

Quantity:
value + UOM + normalized value + conversion source/version.

Evidence:
document id/version, page/paragraph/table/row/column/text span/bounding box when available, confidence, extractor version, timestamp.

Audit:
actor, tenant, timestamp, request/correlation id, object id, action, before/after hashes, reason/comment when required, source system.
