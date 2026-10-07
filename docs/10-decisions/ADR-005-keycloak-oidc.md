<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# ADR-005 - Keycloak OIDC + RLS tenancy

- Context: enterprise SSO/MFA needed with zero license cost.
- Decision: Keycloak self-host OIDC; short JWT + rotating refresh; `tenant_id` RLS + tenant-aware cache/search/storage/logs/AI; isolation tests mandatory.
- Alternatives: Supabase Auth, Auth0, custom JWT.
- Consequences: +free SSO/MFA; −must operate Keycloak (managed IdP swap allowed via OIDC interface).
