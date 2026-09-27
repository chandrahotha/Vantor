# Failure Model

Design for these failures explicitly:

- duplicate API request;
- client timeout after commit;
- process restart mid-request;
- DB failover;
- Redis outage;
- object storage timeout;
- webhook partner timeout/429/5xx;
- identity provider outage/key rotation;
- AI provider timeout/invalid output;
- queue worker crash;
- partial deployment;
- migration failure.

Every command must define whether the outcome is retryable, replayable, or permanently rejected.
