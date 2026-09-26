# Security — AI Supplier Negotiation Simulator

## Required controls
- OIDC/JWT auth pattern inherited from Top-5.
- tenant context established server-side; never trusted from user payload alone.
- role + object authorization on every mutable/read-sensitive endpoint.
- SoD checks before approvals/material actions.
- rate limits on expensive runs and uploads.
- content signature/size/type validation for documents.
- quarantine before extraction for document-driven products.
- secrets only from environment/secret manager.
- structured logs without sensitive commercial or personal data.
- immutable audit for material changes.

## Product-specific threat focus
AI persona hallucination, prompt injection through evidence, unstable scoring, user confusing simulation with factual supplier behavior, accidental live integration.

## Fail-closed rules
Authorization failures, evidence validation failures, schema violations, and approval violations block the requested action. They do not silently downgrade to best effort when the operation is material.
