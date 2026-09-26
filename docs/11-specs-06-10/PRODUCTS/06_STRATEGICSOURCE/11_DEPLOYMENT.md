# Deployment — Strategic Sourcing Optimization Engine

Use the inherited deployment pattern: web on Vercel-compatible runtime; API/worker on controlled container/server runtime; managed PostgreSQL; S3-compatible object storage; Redis/queue when needed; monitoring and structured logs.

## Requirements
- environment variables documented in `.env.example`
- migration procedure documented
- health/readiness probes
- graceful worker shutdown
- retry/dead-letter handling where async jobs exist
- backups and restore test
- synthetic demo environment isolated from production
- no public write access to production databases
- CORS and allowed origins explicitly configured
- rate limits on expensive operations

## Release checklist
Run the product acceptance checklist, integration contract checks and security corpus before deployment.
