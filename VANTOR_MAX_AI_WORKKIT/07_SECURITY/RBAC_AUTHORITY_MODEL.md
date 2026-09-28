<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Rbac Authority Model

Replace broad `WRITE_ROLES` checks with permission checks and authority policies. Model permissions separately from role labels. Support role membership, spend limits, resource scopes, approval tiers, delegation and SoD. Every mutation path must use the same authorization service.

## Now implemented (2026-09-28)

Still open, deliberately: role checks are still broad `*_ROLES` sets, and there is still no
central authorization service — four routers keep their own local `_require` (contracts, spend,
sourcing, suppliers), each with a domain-specific error code. Permission, spend-limit,
delegation and SoD modelling is untouched.

What changed:

- **`Service Identity`, a machine role for the worker.** It covers exactly two operations
  (the contract expiry roll and the webhook drain), is granted to no human, and is
  deliberately not a subset of any human role. A leaked worker token is therefore not an
  administrative token. The previous grant was `Super Admin` + `Procurement Admin` +
  `Procurement Manager`, held only because the expiry roll demanded `Super Admin`.
- **`POST /rfqs/{id}/optimize` had no role gate at all** — the only endpoint in `sourcing`
  that skipped `_write`. It commits an audit event and returns the allocation that decides who
  wins a buy, so any authenticated member, including supplier-side and read-only accounts,
  could harvest that recommendation. Now gated, with tests asserting both the refusals and the
  admissions.
- Reads stay ungated by design: data is separated by tenant, so gating reads would hide a
  buyer's own data from them. All 42 ungated routes were reviewed for consistency rather than
  assumed.
