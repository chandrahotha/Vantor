# Domain Boundaries

Core domains: Supplier, Sourcing, Contract, Requisition, Purchase Order, Receipt, Invoice, Spend Ledger, Document, Approval/Governance, AI, Integration, Notification, Identity/Tenant.

Each aggregate must have one owner for state transitions. Avoid duplicate logic such as the two matching engines that currently overlap.

Cross-domain operations should use explicit application commands, not arbitrary status writes.
