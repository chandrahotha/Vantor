# Integration Adapter Rules

Consumes: RFQLens sourcing event, SupplierRadar risk snapshot, CostPilot cost basis.
Publishes: solution/scenario facts for ProcurementOS and read-only decision inputs for downstream modules.
Contract requirement: all source snapshots carry source product version, schema version and snapshot hash.
