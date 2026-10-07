<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Design System - VANTOR

**Status: `IMPLEMENTED`. Implements `../01-product/requirements.md` §UI quality bar.**

## Tokens
- Color: **Hyper Cobalt `#0038FF`** (primary: CTAs, links, active tabs, key data series, the sidebar), **Skin Sand `#FFD8B8`** (accent: highlights, selected states, badges, onboarding fills), Background `#F8FAFC`, Surface `#FFFFFF`, Primary text `#172033`, Secondary text `#667085`, Border `#E5E7EB`. Status: info blue, warn amber `#F59E0B`, danger `#EF4444`, success emerald.
- Skin Sand never carries text on a light surface - it is 1.3:1 on white, so it paints fills only. Accent *text* is `--accent-ui`, the sand accent made readable.
- The sidebar is the brand anchor: Hyper Cobalt in every palette and both modes, white labels and icons, and the active route in Skin Sand with cobalt text.
- Type: Inter (UI) + JetBrains Mono (numbers/code); scale 12/14/16/20/24/32; tabular numerals in grids.
- Spacing 4pt base; radius 6/8/12; elevation 0/1/2/3; borders `1px slate-200/800`.
- Five palettes × light/dark on the gated CSS token layer (`app/globals.css`, audited by `frontend/check_palette_layer.py`): the default is Vantor Cobalt, then Sourcing Emerald, Contract Sapphire, Spend Amber and Negotiation Obsidian as alternate workspace themes. The sidebar stays cobalt under every palette.

## Components (reusable library, Phase 7)
Buttons, inputs, selects, tables/data-grid (sort/filter/pin/group/saved-views/export/bulk/keyboard), dialogs, drawers, command palette (`Ctrl+K`), toasts, badges/status, skeletons, empty/error states, charts (real data only), confirmation patterns.

## Rules
No bootstrap-generic cards, no gradient soup, no glassmorphism, no meaningless animation. Density without clutter; keyboard-first; `prefers-reduced-motion` respected. See also: Brain → `../06-brand/logo.md`, `../07-android/strategy.md`.
