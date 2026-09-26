# Security Test Corpus for Products 06–10

Every applicable product must test:

- tenant crossover attempts
- object-ID enumeration
- stale/expired authz
- privilege escalation
- SoD violations
- request replay/idempotency collisions
- malformed spreadsheets and macros
- XXE / entity expansion
- zip bombs / decompression abuse
- path traversal
- stored/reflected XSS
- prompt injection in uploaded documents and text fields
- SSRF-looking URLs if external connectors exist
- secret-like strings in logs/exports
- oversized requests/uploads
- broken content type/signature validation
- AI schema corruption and evidence mismatch
- adversarial numerical values: negative prices, impossible quantities, overflow, extreme percentages
