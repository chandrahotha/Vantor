<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Portfolio — the 10 products inside VANTOR

**Status: `IN DEVELOPMENT`. This page is the single canonical product list for VANTOR.**

VANTOR consolidates **ten** products from the ProcurementAI portfolio into one modular
monolith. Nine of the ten ship as native VANTOR modules; one (ProcurementOS Agent) is
realised as the AI/HITL/approval substrate the others call.

> **Why ten and not five.** The original brief (`../00-plan/masterdoc.md`) and the
> Phase 0 audit scope were **five private repositories** — products 01–05. Products
> 06–10 arrived later as a vendored build-brain (`../11-specs-06-10/`). Any doc that
> still says "five products" is describing the *audit scope*, not the product.

## The ten

| # | Product | Origin | VANTOR module | Deterministic core | Status |
|---|---|---|---|---|---|
| 01 | ProcurementOS Agent | repo `ProcurementOS-Agent` | `app/services/ai_tools.py`, `ai_gateway.py`, `routers/ai.py` | typed tool registry + HITL approvals | `IN DEVELOPMENT` |
| 02 | RFQLens | repo `RFQLens--QuotientX` | `app/routers/sourcing.py`, `services/optimizer.py` | RFQ→quote→award, greedy split optimizer | `TESTED` |
| 03 | CostPilot | repo `CostPilot-Costryn` | `app/routers/spend.py`, `services/should_cost.py` | integer-minor should-cost + quote gap | `TESTED` |
| 04 | ContractGuard | repo `ContractGuard-Veridox` | `app/routers/contracts.py`, `services/matching.py` | 11-dim match, obligations, e-sign records | `TESTED` |
| 05 | SupplierRadar | repo `SupplierRadar--Valtrix` | `app/routers/suppliers.py`, `services/scoring.py` | 5-dim scorecard → grade + risk tier | `TESTED` |
| 06 | Strategic Sourcing Optimization | spec `PRODUCTS/06_STRATEGICSOURCE` | `services/optimizer.py` (via `sourcing.py`) | share-capped allocation + violation report | `IN DEVELOPMENT` |
| 07 | Procurement Spend Intelligence | spec `PRODUCTS/07_SPENDINTEL` | `services/spend_intel.py` (via `spend.py`) | cube, leakage, maverick, concentration | `IN DEVELOPMENT` |
| 08 | Supplier Onboarding & Qualification | spec `PRODUCTS/08_SUPPLIERONBOARD` | `routers/suppliers.py` qualification routes | certs→scorecard→checklist→SoD decision | `IN DEVELOPMENT` |
| 09 | PO Price Intelligence | spec `PRODUCTS/09_POPRICE` | `services/price_intel.py` (via `spend.py`) | median baseline, variance split, case handoff | `IN DEVELOPMENT` |
| 10 | AI Supplier Negotiation Simulator | spec `PRODUCTS/10_NEGOSIM` | `services/negosim.py` (via `ai.py`) | concession ladder + walk-away floor | `IN DEVELOPMENT` |

## What each status means

- `TESTED` — the module's core path is implemented and covered by the backend suite
  (`backend/tests/`), with no mock data. Products 01–05 are at this level for their
  primary flows; the Phase 0/3/4 gates are `PASSING` (see `../00-plan/ROADMAP.md`).
- `IN DEVELOPMENT` — implemented with golden-vector tests, but the product's **full spec
  acceptance suite has not been run** and its **UI is not complete**. Products 06–10 are
  all here: Phase 11 gates them on `08 → 09 → 07 → 06 → 10`.
- Nothing in VANTOR is `PRODUCTION READY`. Phase 10 owns that gate.

## What is deliberately not claimed

- **No product is "done".** No entry above may be read as a shipped feature.
- **Documents 06–10 have no OCR/embed/analyze/evidence/review stage yet** — the Phase 5
  pipeline is partial (`validate → store → extract → chunk` are real; OCR, embedding,
  semantic index, analysis, evidence and review are absent). See `../00-plan/ROADMAP.md` Phase 5.
- **`/api/ai/stream` is SSE-framed, not provider-streamed** — the upstream call completes
  before the first frame. README keeps "live-LLM streaming" in the not-done list.
- **The UI exposes 16 of 75 API operations.** Write paths (RFQ create/award, PO
  approve/send/receipt/invoice, catalog, budgets, integrations, audit) are API-only today.

## Portfolio flow

```
01 ProcurementOS Agent  ←── HITL decisions, typed tools, orchestrator
        ▲
   ┌────┴─────────────────────────────┐
   │                                   │
02 RFQLens ──→ 06 Strategic Sourcing ──┘
   │                   ▲
03 CostPilot ──────────┤
   │                   │
04 ContractGuard ──→ 09 PO Price Intel
   │                   │
05 SupplierRadar ←── 08 Supplier Onboarding
   │
07 Spend Intelligence ──→ strengthens 02, 03, 05
   │
10 Negotiation Simulator ←─ consumes 02 + 03 + 05 (simulation only, never auto-applies)
```

Upstream portfolio map (vendored, read-only): `../11-specs-06-10/PORTFOLIO_MAP_01-10.md`.

## Portfolio rule (inherited, still binding)

Products integrate only through typed, versioned APIs and exported schemas — no sibling
source imports, no direct sibling DB reads. VANTOR satisfies this structurally: one
modular monolith, strict module boundaries ([ADR-001](../10-decisions/ADR-001-modular-monolith.md)),
typed AI tools ([ADR-004](../10-decisions/ADR-004-typed-ai-tools.md)). Within a module,
product logic lives in `backend/app/services/` and never reaches into another module's
tables directly.
