# Tenant Isolation

Enforce tenant isolation at three levels: JWT-to-request tenant binding, every query/write scoped to tenant, PostgreSQL RLS where appropriate. Add cross-tenant attack tests for every resource type and every route family.
