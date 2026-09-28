<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Keycloak Bootstrap

Provision realm, clients, roles, scopes, audience, redirect URIs, service accounts and signing-key rotation. Never use `start-dev` in production.

## Now implemented (2026-09-28)

`deploy/keycloak/provision.py` provisions the realm from the `realm-vantor.json` export:
14 realm roles, the public `vantor-web` client, and the `vantor-service` client with its
service account. The service account is granted **exactly one** role, `Service Identity`, and
`tests/test_realm_parity.py` fails if the grant, the realm role definitions and the JSON export
ever drift apart — the export being a checked artifact is the point, since a role added to
Keycloak by hand is invisible to CI.

`Service Identity` is described in the realm as a machine identity and is not a subset of any
human role, so an operator reading the realm can tell at a glance whether granting it is safe.
It replaced a grant of `Super Admin` + `Procurement Admin` + `Procurement Manager`.

Still open: signing-key rotation, scopes and audience mappers beyond the default realm roles, and
the "never `start-dev`" production rule, which is documented but not enforced by a gate.
