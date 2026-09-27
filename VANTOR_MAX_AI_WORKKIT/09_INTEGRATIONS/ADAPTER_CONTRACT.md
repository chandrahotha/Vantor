# Adapter Contract

Adapters expose typed operations and explicit error classes: auth failure, timeout, rate limit, invalid payload, transient upstream, permanent upstream. Never let provider-specific exception strings leak into business logic.
