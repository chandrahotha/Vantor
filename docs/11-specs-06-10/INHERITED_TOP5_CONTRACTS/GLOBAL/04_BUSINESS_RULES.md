# Global Business Rules

## Quote normalization
Canonical fields:
supplier, item, quantity, UOM, unit_price, currency, tax_mode, freight, insurance, tooling, discounts, payment_terms, lead_time, delivery_terms, Incoterm, warranty, validity.

Normalized total is configurable and must avoid double counting taxes/freight.

## Supplier KPIs
OTD = on-time eligible deliveries / eligible deliveries.
Quality acceptance = accepted quantity / received quantity.
PPM = rejected units / received units × 1,000,000.

Every KPI exposes numerator, denominator, period, exclusions and source.

## Risk
Risk score is a configurable analytical model, not an objective fact.
Store dimensions, weights, thresholds, source data and version.

## Sourcing
Scenario defines demand, supplier eligibility, capacity, allocation limits, price model, quality/delivery/risk constraints and objective.
No scenario is automatically approved.

## Compliance
Contract → PO → invoice matching covers supplier, item, quantity, price, currency, tax mode, payment, delivery, Incoterm, dates and references.
Results are exact / within tolerance / exception / unknown / not applicable.

## Missing data
Unknown is not zero.
Stale data is explicitly labeled.
Confidence is not correctness.
