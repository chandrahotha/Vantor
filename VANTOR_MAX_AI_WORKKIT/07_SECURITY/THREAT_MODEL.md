# Threat Model

Threat actors: tenant user with legitimate access, compromised tenant admin, malicious supplier/integration endpoint, malicious uploaded document, compromised third-party AI/integration, external attacker.

Trust boundaries: browser->API, API->Keycloak, API->Postgres, API->Redis, API->object storage, API->AI provider, worker->API, worker->external webhooks.

High-risk assets: procurement amounts, supplier data, contracts, credentials/API keys, documents, approval authority, audit history.
