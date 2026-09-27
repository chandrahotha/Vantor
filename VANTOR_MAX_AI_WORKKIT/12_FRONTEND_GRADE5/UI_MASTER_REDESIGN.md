# Grade-5 UI Master Redesign

## Current problem

The current UI is functional but visually and operationally reads like a lightweight admin console. The redesign must create an **enterprise procurement operating system** rather than a more decorative version of the same tables.

## Design goals

1. Clear decision hierarchy: what needs attention now, why, financial impact, owner, due date, next action.
2. Dense but breathable data presentation.
3. One interaction vocabulary across every module.
4. Zero surprise mutations: destructive/financial actions require explicit confirmation and show authority context.
5. Deep drill-down from KPI -> list -> detail -> source evidence/audit.
6. First-class keyboard navigation and command palette.
7. Desktop-first enterprise usability with strong tablet/mobile adaptation.
8. Consistent empty/loading/error/partial-data states.

## Required visual system

- 8pt spacing scale with tighter data-grid density options.
- semantic color tokens, not page-local values;
- a single high-quality icon library with accessible labels;
- typography hierarchy for KPI / section / table / metadata;
- standardized surface/elevation/radius tokens;
- motion used only to clarify state changes;
- charts and visualizations for spend/risk/trends where they add signal;
- responsive side navigation that collapses to a command-driven mobile shell.

## Enterprise patterns required

Command palette, global search, saved filters, table column chooser, bulk actions, sticky table headers, row action menus, drawers, modal confirmations, timeline/audit view, contextual assistant, inline edit for safe fields, optimistic UI only for idempotent low-risk actions, server-confirmed state for financial actions.

## “Grade-5” acceptance

A reviewer should be able to complete a procurement task without hunting for the next step, understand the consequences before committing, and recover cleanly from partial failures.
