<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Concurrency Tests

Required races: two PO approvals against one budget, two receipts on one PO line, two invoice approvals on same received quantity, two identical idempotency-key requests, two PO sends, two RFQ awards. Run against PostgreSQL with realistic isolation.
