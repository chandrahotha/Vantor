# 18 Ci Cd Supply/Pipeline Gates

Required gates: secret scan -> lint/typecheck -> unit -> PostgreSQL integration -> migration tests -> API contract -> frontend build -> E2E -> a11y -> visual -> dependency/container scan -> SBOM -> image signing -> deploy smoke -> rollback readiness.
