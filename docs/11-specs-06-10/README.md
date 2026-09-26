<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Product Specs 06–10 — ProcurementAI Portfolio Extension

**Status: `REFERENCE` — third-party build-brain vendored verbatim; Vantor implements these as native modules.**

Source bundle: `ProcurementAI_MAX_Build_Brain_Products_06-10` (255 spec docs + manifest).
Vendored trees below are **read-only inputs — never edit them**. Vantor's own
build order and verdicts live in `../00-plan/ROADMAP.md` (Phase 11) and future ADRs.

## Portfolio rule (inherited)

Products 06–10 integrate with 01–05 only through typed, versioned APIs/events and
exported contract schemas — no sibling source imports, no direct sibling DB reads.
Vantor satisfies this structurally: one modular monolith, strict module boundaries
(ADR-001), typed `/api/v1` tools (ADR-004).

## The five

| # | Spec | Vantor module | Inputs it consumes | Outputs |
|---|---|---|---|---|
| 06 | [Strategic Sourcing](PRODUCTS/06_STRATEGICSOURCE/00_PRODUCT_README.md) | `sourcing/` optimizer | RFQ/quotes, should-cost, risk, capacity, MOQ, policies | scenarios, allocations, landed cost, sensitivity, decision package |
| 07 | [Spend Intelligence](PRODUCTS/07_SPENDINTEL/00_PRODUCT_README.md) | `spend/` analytics | POs, invoices, categories, contracts, history | spend cube, leakage, maverick cases, savings, concentration |
| 08 | [Supplier Onboarding](PRODUCTS/08_SUPPLIERONBOARD/00_PRODUCT_README.md) | `supplier/` onboarding | registrations, certs, tax/bank/insurance, ESG | profile, evidence map, scorecard, gaps, approval routing |
| 09 | [PO Price Intelligence](PRODUCTS/09_POPRICE/00_PRODUCT_README.md) | `purchase/` price intel | PO lines, history, contracts, benchmarks | baseline, anomalies, variance split, leakage, handoff cases |
| 10 | [Negotiation Simulator](PRODUCTS/10_NEGOSIM/00_PRODUCT_README.md) | `ai/` simulator | supplier facts, quotes, cost positions, objectives | rounds, responses, concession effects, debrief |

## Vantor build order (decided)

`08 → 09 → 07 → 06 → 10` — extends built modules first (supplier, purchase, spend,
sourcing), simulator last (needs everything + HITL). Each ships with its spec's
golden test matrix + acceptance criteria as gates; truth hierarchy stands
(deterministic math = record, AI = advisory until approved, no real supplier data seeded).

## Bundle contents

- [`PRODUCTS/`](PRODUCTS/) — per-product specs (architecture, data model, business logic, AI, API, security, tests, acceptance, seeds, algorithms, screens)
- [`00_PORTFOLIO_BRAIN/`](00_PORTFOLIO_BRAIN/) — portfolio-level brain
- [`INHERITED_TOP5_CONTRACTS/`](INHERITED_TOP5_CONTRACTS/) — read-only Top-5 contract snapshot (compare before implementing; fail closed on incompatibility)
- [`MANIFEST.json`](MANIFEST.json), [`PORTFOLIO_MAP_01-10.md`](PORTFOLIO_MAP_01-10.md), [`START_HERE_LLM.md`](START_HERE_LLM.md), [`MAX_BRAIN_CHANGELOG.md`](MAX_BRAIN_CHANGELOG.md)
