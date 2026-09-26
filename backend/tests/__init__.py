"""Phase 3 gate tests — must stay green without external Postgres/Keycloak.

- test_health: envelope + request-ID.
- test_audit_chain: hash chain + tamper detection (sqlite).
- test_tenant_isolation: cross-tenant invisibility at query + RLS-SQL level.
- test_auth: real RS256 verification with generated keys, fail-closed paths.
"""
