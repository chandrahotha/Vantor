# P03 Data Quality

Product: Procurement Spend Intelligence Agent

## Purpose
Primary workflow screen for p03 data quality.

## UI requirements
- inherited enterprise shell and design tokens
- dense procurement table patterns where records are tabular
- filters/search/sort with server-side pagination where data is large
- clear status chips and exception-first layout
- role-sensitive actions
- inline validation before submission
- loading, empty, partial, error, denied and stale/processing states

## User actions
Primary action must reflect the current state machine; destructive or material actions require confirmation and approval as defined by policy.

## Audit
Record material create/update/decision actions with actor, object, reason where required and request id.
