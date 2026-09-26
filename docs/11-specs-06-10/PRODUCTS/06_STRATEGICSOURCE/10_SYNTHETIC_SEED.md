# Synthetic Seed — Strategic Sourcing Optimization Engine

Create a deterministic demo tenant named `SYN-STRATEGICSOURCE`. Every row must carry `is_synthetic=true` where practical.

## Required fixture families
- clean happy-path case
- incomplete/missing-data case
- contradictory-data case
- stale-data case
- high-volume case
- unauthorized-access case
- AI-unavailable case
- idempotent-retry case
- export-failure case

## Demo reset
Provide a single documented reset command that recreates the same seed, same identifiers where feasible, and same result hashes for deterministic workflows.
