# Service Identity

Workers should authenticate with workload identity/client credentials, not a manually copied long-lived bearer token in `.env`. Token acquisition and refresh belong to the worker identity layer.
