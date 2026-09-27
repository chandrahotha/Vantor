<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Secrets

No production secrets in `.env` files committed to source. Use secret manager/workload identity. Rotate OIDC client secrets, provider keys and object-storage credentials. Never log authorization headers, API keys or document contents.
