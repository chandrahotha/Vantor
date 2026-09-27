# Postgres Required

SQLite is useful for fast logic tests but cannot substitute for PostgreSQL locking, RLS, index/query plans and migration behavior. CI must have required PostgreSQL infrastructure for release gates.
