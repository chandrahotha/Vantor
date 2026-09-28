<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Timezone

Tenant/business/user timezone hierarchy. Store instants in UTC; compute business dates and due periods in the relevant timezone. Handle DST explicitly where applicable.

## Now implemented (2026-09-28)

Instants are stored in UTC throughout, and business dates are computed in the **tenant's own**
timezone rather than the server's. This matters for correctness, not presentation: "within 90
days" was evaluated against one deployment-wide `CONTRACT_TIMEZONE`, so a buyer at UTC-12
reached their own 1 January twelve hours before a UTC server did and the renewal notice fired a
day early or late — and the tenants of a procurement system are normally in different countries,
so a single deployment-wide zone is wrong for nearly all of them.

- `organizations.timezone` holds an IANA zone per tenant. Empty means "inherit". Migration
  `0023_tenant_timezone` backfills empty, so upgrading an existing row changes nothing.
- Resolution order is tenant → deployment (`CONTRACT_TIMEZONE`) → UTC. An unusable zone at any
  level falls through to the next rather than raising, because a stale contract status is
  recoverable and a queue that stops draining is not.

Still open: the hierarchy is tenant/deployment only — there is no per-user timezone. DST is
handled by `zoneinfo` for whatever zone resolves, but there is no explicit rule of its own.
A tenant that changes its zone mid-period will see the "within 90 days" boundary move, which is
correct behaviour but is not surfaced anywhere.
