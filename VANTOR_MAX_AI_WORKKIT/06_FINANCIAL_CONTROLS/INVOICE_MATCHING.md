<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Invoice Matching

Canonical invoice matching must combine PO, receipts, current invoice, and every prior approved/accepted invoice line.

For each PO line:
`prior_approved_qty + current_qty <= received_qty <= ordered_qty`

Also verify supplier, currency, line price, line arithmetic, invoice total and contract/date coverage where applicable. The same matcher must be used by live approval and by standalone match reporting.
