<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Service Identity

Workers should authenticate with workload identity/client credentials, not a manually copied long-lived bearer token in `.env`. Token acquisition and refresh belong to the worker identity layer.
