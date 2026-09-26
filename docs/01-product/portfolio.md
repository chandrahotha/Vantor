<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Portfolio — the 10 products inside VANTOR

**Status: `TESTED` — all 10 products now pass their core-path tests on the live stack
(113 backend tests green, 35 frontend vitest green).** Full Phase-11 vendor-spec acceptance
suites are planned as Phase 11 gates.

VANTOR consolidates **ten** products from the ProcurementAI portfolio into one modular
monolith. Nine of the ten ship as native VANTOR modules; one (ProcurementOS Agent) is
realised as the AI/HITL/approval substrate the others call.

> **Why ten and not five.** The original brief (`../00-plan/masterdoc.md`) and the
> Phase 0 audit scope were **five private repositories** — products 01–05. Products
> 06–10 arrived later as a vendored build-brain (`../11-specs-06-10/`). Any doc that
> still says "five products" is describing the *audit scope*, not the product.

## The ten (verified state)

| # | Product | VANTOR module | UAT signal | Test evidence | Status |
|---|---|---|---|---|---|
| 01 | ProcurementOS Agent | `services/ai_tools.py`, `ai_gateway.py`, `routers/ai.py`, `worker/beat.py` | `/copilot` + `/negosim` + evidence frames | test_ai(7) + hitl_stream(5) + ai_eval(8) + e2e | `TESTED` |
| 02 | RFQLens | `routers/sourcing.py`, `services/optimizer.py` | `/rfqs`, `/requisitions` | test_sourcing(2) + optimizer(4) + e2e | `TESTED` |
| 03 | CostPilot | `routers/spend.py`, `services/should_cost.py` | `/spend` (calculator) | test_should_cost(6) + price_intel(2) | `TESTED` |
| 04 | ContractGuard | `routers/contracts.py`, `services/matching.py` | `/contracts` | test_contracts(2) + test_matching(4) | `TESTED` |
| 05 | SupplierRadar | `routers/suppliers.py`, `services/scoring.py` | `/suppliers`, `/suppliers/[id]` | test_suppliers(5) + scoring(4) + onboarding(1) | `TESTED` |
| 06 | Strategic Sourcing Optimization | `services/optimizer.py` (via `sourcing.py`) | `/rfqs` "Suggest allocation" | test_optimizer(4) golden vectors | `TESTED` |
| 07 | Procurement Spend Intelligence | `services/spend_intel.py` (via `spend.py`) | `/spend` | test_spend_intel(2) + e2e asserts | `TESTED` |
| 08 | Supplier Onboarding & Qualification | `routers/suppliers.py` qualification routes | `/suppliers/[id]` workflow | onboarding(1) + e2e | `TESTED` |
| 09 | PO Price Intelligence | `services/price_intel.py` (via `spend.py`) | `/orders` "Price check" | test_price_intel(2) + e2e | `TESTED` |
| 10 | AI Supplier Negotiation Simulator | `services/negosim.py` (via `ai.py`) | `/negosim` | test_negosim(5) | `TESTED` |

## What each status means

- `TESTED` — the module's core path is implemented and covered by the backend suite
  (`backend/tests/`), with no mock data, and the UI path exists for its primary flows.
  Phase 0/3/4 gates are `PASSING` (see `../00-plan/ROADMAP.md`).
- `IN DEVELOPMENT` — no longer used for the products table. Reserved for Phase 11
  vendor acceptance suites (the spec's own golden matrices) and UI wave 2 polish.
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
