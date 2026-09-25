<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Design System — VANTOR

**Status: `PLANNED`. Implements `../01-product/requirements.md` §UI quality bar.**

## Tokens
- Color: Deep Navy `#0A1931` (brand bg), Electric Blue `#1B6CFF` (primary), Cyan `#22D3EE` (accents/links), Emerald `#10B981` (success/savings), Slate `#64748B` (secondary), White `#FFFFFF` + dark surfaces `#0F1F3D`. Status: info blue, warn amber `#F59E0B`, danger `#EF4444`.
- Type: Inter (UI) + JetBrains Mono (numbers/code); scale 12/14/16/20/24/32; tabular numerals in grids.
- Spacing 4pt base; radius 6/8/12; elevation 0/1/2/3; borders `1px slate-200/800`.

## Components (reusable library, Phase 7)
Buttons, inputs, selects, tables/data-grid (sort/filter/pin/group/saved-views/export/bulk/keyboard), dialogs, drawers, command palette (`Ctrl+K`), toasts, badges/status, skeletons, empty/error states, charts (real data only), confirmation patterns.

## Rules
No bootstrap-generic cards, no gradient soup, no glassmorphism, no meaningless animation. Density without clutter; keyboard-first; `prefers-reduced-motion` respected. See also: Brain → `../06-brand/logo.md`, `../07-android/strategy.md`.
