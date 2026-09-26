# P07 Anomaly Analysis

Product: PO Price Intelligence Engine

## Purpose
Primary workflow screen for p07 anomaly analysis.

## UI requirements
- inherited enterprise shell and design tokens
- dense procurement table patterns where records are tabular
- filters/search/sort with server-side pagination where data is large
- clear status chips and exception-first layout
- role-sensitive actions
- inline validation before submission
- loading, empty, partial, error, denied and stale/processing states

## Evidence / explainability
Show source facts, rules, calculation basis, timestamps and links to evidence. Clearly label AI-generated explanation where present.

## User actions
Primary action must reflect the current state machine; destructive or material actions require confirmation and approval as defined by policy.

## Audit
Record material create/update/decision actions with actor, object, reason where required and request id.
