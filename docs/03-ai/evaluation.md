<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# AI Evaluation - VANTOR

**Status: `PLANNED`. No AI change ships without eval regression.**

## Metrics
Factual accuracy, evidence/citation correctness, hallucination rate, extraction/classification accuracy, tool-selection accuracy, policy compliance, injection resistance, latency, cost per task.

## Datasets (build Phase 6)
- Contract extraction (clauses/obligations/renewals) with page-level gold labels.
- Quote comparison with normalized totals + award rationale.
- Spend anomaly with known injected anomalies.
- Injection/adversarial suite (direct + indirect).
- Regression prompts pinned per release.

## Gates
- Extraction F1 ≥ target (set after baseline), citation precision ≥ 0.95 on contract tasks, injection block rate 100% on critical suite, cost/latency within tenant budgets.
- Results stored per model version; rollback on regression.
