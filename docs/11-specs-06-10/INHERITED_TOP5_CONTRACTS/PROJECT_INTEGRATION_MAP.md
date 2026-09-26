# Integration Map

Shared services:
documents → evidence → supplier → price history → rules → calculations → AI orchestration → reports → approval → audit.

RFQLens creates:
RFQ, RFQLine, SupplierQuote, SupplierQuoteLine, SourcingScenario.

SupplierRadar consumes:
Supplier, SupplierMetric, historical delivery/quality and risk signals.

CostPilot consumes:
Item, PriceHistory, CostModel, SupplierQuote.

ContractGuard consumes:
Supplier, Contract, PO-like records, Invoice-like records, RuleSet.

ProcurementOS Agent orchestrates:
RFQLens + SupplierRadar + CostPilot + ContractGuard through typed read/analysis tools.
