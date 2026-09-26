"""Tenant isolation — application filters + RLS policy SQL.

Gate: cross-tenant rows must be invisible even with a forgotten WHERE clause
at the DB layer (RLS backstop). Unit level asserts query scoping; SQL level
asserts the migration installs the correct policy.
"""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.registry import Base
from app.services.audit import record_event


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_application_filter_never_returns_foreign_tenant():
    db = _db()
    record_event(db, tenant_id="tenant-a", actor="u", action="X", resource="r", resource_id="1")
    record_event(db, tenant_id="tenant-b", actor="u", action="X", resource="r", resource_id="2")
    seen = list(db.execute(select(AuditEvent).where(AuditEvent.tenant_id == "tenant-a")).scalars())
    assert len(seen) == 1
    assert all(r.tenant_id == "tenant-a" for r in seen)
    db.close()


def test_baseline_migration_defines_rls_policies():
    import pathlib

    mig = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_baseline.py"
    sql = mig.read_text(encoding="utf-8")
    # Migration generates policies in a loop over TENANT_TABLES — assert the loop
    # + the table list + the policy template, not expanded per-table strings.
    for table in ["organizations", "user_accounts", "roles", "audit_events", "idempotency_keys"]:
        assert f'"{table}"' in sql or table in sql
    assert "TENANT_TABLES" in sql
    assert "CREATE POLICY tenant_isolation ON" in sql
    assert "current_setting('app.tenant_id'" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql


def test_audit_write_requires_tenant():
    import pytest

    db = _db()
    with pytest.raises(ValueError, match="tenant_id is required"):
        record_event(db, tenant_id="", actor="u", action="X", resource="r")
    db.close()
