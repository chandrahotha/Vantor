<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Service Identity

Workers should authenticate with workload identity/client credentials, not a manually copied long-lived bearer token in `.env`. Token acquisition and refresh belong to the worker identity layer.

## Now implemented (2026-09-28)

The worker uses Keycloak client credentials for the `vantor-service` client, granted the
dedicated `Service Identity` realm role. No long-lived bearer token is stored in `.env`.

**The role is the design.** It covers exactly the two operations the worker performs — the
contract expiry roll and the webhook delivery drain — and nothing else. It is deliberately *not*
a subset of any human role, which is what makes the least-privilege claim checkable: "the worker
can do X" and "a person can do X" are independent statements, and a test can assert the first
without the second being true.

The previous arrangement was a grant of `Super Admin`, `Procurement Admin` and
`Procurement Manager`, needed only because the expiry roll's `Super Admin` requirement. Those
secrets live in the environment of two containers, so a leaked environment was a fully
administrative token. `test_realm_parity.py` asserts the grant is exactly one role, that no
human role set includes `Service Identity`, that both worker operations are still reachable, and
that activate/terminate/sign/review/renew/approve are refused.

**Residual scope, stated rather than hidden:** a leaked service token reaches the tenant its
token belongs to. The right mitigation is one service account per tenant, not a wider role.
And because the worker drains through the tenant-scoped route, a single worker delivers only
its own tenant's webhooks — a cross-tenant drain would need its own explicitly cross-tenant
identity, not a broadened `Service Identity`.
