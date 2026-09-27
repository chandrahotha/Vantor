# Budget Atomicity

Budget checks are reservations, not informational reads. Lock the budget period or use an atomic conditional update. A reservation must have a lifecycle: reserved -> consumed -> released/adjusted. All transitions must reconcile with PO status.
