<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../BRAIN.md) · [Docs index](../README.md)

# Data Processing Agreement — VANTOR (DRAFT)

> **This is an unreviewed draft, not a published legal document.** It has not
> been reviewed by a lawyer. Every `[TO CONFIRM]` is a real gap — see
> `LEGAL-INFO-REQUIRED.md`.

## When this document applies

**Under the self-hosted distribution model described in `terms-of-service.md`,
this DPA does not apply.** An organization that downloads and runs VANTOR
itself is the sole controller and processor of the data in its own
deployment — Digi Tracks never receives or processes that data, so there is
no processing relationship for a DPA to govern.

This document becomes relevant only if Digi Tracks offers a **hosted or
managed version of VANTOR**, where Digi Tracks would process a customer's
data on that customer's behalf. `[TO CONFIRM: does this offering exist or is
it planned?]` If not, this file should stay a placeholder (or be removed)
rather than be published as a binding agreement for a service that does not
exist.

## If a hosted offering exists, this DPA needs real terms for:

1. **Subject matter and duration** — the processing covered, and how long this
   agreement runs (tied to the underlying services agreement). `[TO CONFIRM]`
2. **Nature and purpose of processing** — hosting and operating VANTOR on the
   customer's behalf. `[TO CONFIRM: any processing beyond hosting, e.g.
   support access to customer data?]`
3. **Categories of data and data subjects** — the data a customer's tenant
   stores in VANTOR is defined by the customer (suppliers, employees,
   contracts, spend records, etc.); the data subjects are the customer's own
   personnel and counterparties. `[TO CONFIRM: any special categories of data
   expected?]`
4. **Sub-processors** — infrastructure providers Digi Tracks would use to
   operate the hosted service (hosting provider, database provider, etc.).
   `[TO CONFIRM — list each one]`
5. **Security measures** — this repository documents the controls the
   software itself implements (OIDC/local auth, RBAC, tenant-scoped row-level
   security on Postgres, hash-chained audit log, encrypted transport — see
   `../04-security/architecture.md` and `../../SECURITY.md`); the DPA should
   state which of these apply to the hosted environment specifically, plus any
   operational controls (backups, access control, incident response).
   `[TO CONFIRM: hosted-environment specifics — the architecture doc describes
   the software, not Digi Tracks's own operational practices]`
6. **Data subject rights assistance** — how Digi Tracks would help the
   customer respond to access/deletion/export requests from the customer's
   own data subjects. `[TO CONFIRM]`
7. **Breach notification** — timeline and method for notifying the customer of
   a security incident affecting their data. `[TO CONFIRM: e.g. "without
   undue delay" is a common standard — confirm the actual commitment]`
8. **Data return and deletion** — what happens to the customer's data at the
   end of the relationship. `[TO CONFIRM: retention period before deletion,
   format for data return]`
9. **Audit rights** — whether and how a customer may audit Digi Tracks's
   compliance with this agreement. `[TO CONFIRM]`
10. **International transfers** — if data crosses borders, the transfer
    mechanism relied on (e.g. standard contractual clauses). `[TO CONFIRM:
    depends on where the hosted service and its customers are located]`

---

*This document is a draft intended to be reviewed and completed by Digi
Tracks and a qualified legal professional before publication. It is not legal
advice.*
