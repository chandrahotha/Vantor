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


def test_all_migrations_enforce_rls_on_created_tables():
    """B-06: Every table created in any migration must have RLS enabled and a tenant_isolation policy.

    Prevents any new tenant table from being introduced without the mandatory
    row-level security backstop.
    """
    import ast
    import pathlib
    import re

    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    created_tables: dict[str, str] = {}
    tables_with_rls: set[str] = set()
    tables_with_policy: set[str] = set()

    for path in sorted(versions.glob("*.py")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")

        for m in re.finditer(r'op\.create_table\(\s*["\']([^"\']+)["\']', text):
            created_tables[m.group(1)] = path.name

        tables_list: list[str] = []
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ("TABLES", "TENANT_TABLES"):
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    tables_list.append(elt.value)

        if "ENABLE ROW LEVEL SECURITY" in text:
            if "for table in TABLES" in text or "for table in TENANT_TABLES" in text:
                for t in tables_list:
                    tables_with_rls.add(t)
            for m in re.finditer(r"ALTER TABLE\s+([a-zA-Z0-9_]+)\s+ENABLE ROW LEVEL SECURITY", text):
                tables_with_rls.add(m.group(1))

        if "CREATE POLICY tenant_isolation" in text:
            if "for table in TABLES" in text or "for table in TENANT_TABLES" in text:
                for t in tables_list:
                    tables_with_policy.add(t)
            for m in re.finditer(r"CREATE POLICY tenant_isolation ON\s+([a-zA-Z0-9_]+)", text):
                tables_with_policy.add(m.group(1))

    # Allowlist for tables that legitimately do not have tenant RLS (all 40 tables are tenant-isolated)
    allowed_no_rls: set[str] = set()

    missing_rls = set(created_tables.keys()) - tables_with_rls - allowed_no_rls
    assert not missing_rls, f"Tables missing ENABLE ROW LEVEL SECURITY: {sorted(missing_rls)}"

    missing_policy = set(created_tables.keys()) - tables_with_policy - allowed_no_rls
    assert not missing_policy, f"Tables missing CREATE POLICY tenant_isolation: {sorted(missing_policy)}"



def test_audit_write_requires_tenant():
    import pytest

    db = _db()
    with pytest.raises(ValueError, match="tenant_id is required"):
        record_event(db, tenant_id="", actor="u", action="X", resource="r")


import pytest as _pytest  # noqa: E402  (grouped with the live-Postgres test below)


def _token(pem: bytes, tenant: str) -> dict:
    from datetime import datetime, timedelta, timezone

    import jwt

    now = datetime.now(timezone.utc)
    tok = jwt.encode(
        {
            "iss": "https://issuer.test/realms/vantor",
            "aud": "vantor-web",
            "sub": f"u-{tenant}",
            "tenant_id": tenant,
            "realm_access": {"roles": ["Buyer", "Procurement Manager"]},
            "exp": now + timedelta(minutes=5),
            "iat": now,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "pg-kid"},
    )
    return {"Authorization": f"Bearer {tok}"}


@_pytest.mark.pg
def test_tenant_a_cannot_read_tenant_bs_row_through_the_real_app_connection(pg_client):
    """The live, behavioural proof the suite was missing.

    Every other Postgres-tier test either checks migration/model drift or a
    *reference-integrity* guard (can tenant A's row point at tenant B's row).
    None of them had ever asked the more basic question this one does: with
    the application's own database role (not the migration owner), can tenant
    A's request simply list a row tenant B created? Before migration
    0026_app_role_least_privilege, the application connected as a Postgres
    superuser, which Postgres never subjects to row-level security regardless
    of FORCE ROW LEVEL SECURITY — every `tenant_isolation` policy in this
    schema was a no-op for the app's own queries, and this test would have
    passed anyway only because it was never run against the role that
    mattered. It now runs through `pg_client`, which points the app at the
    restricted `vantor_app` role.
    """
    from tests.pgsupport import purge_tenant

    c, pem, tenant_a = pg_client
    tenant_b = f"{tenant_a}-other"

    created = c.post(
        "/api/v1/suppliers", json={"code": "TENANT-B-ONLY", "name": "Only Tenant B"}, headers=_token(pem, tenant_b)
    )
    assert created.status_code == 201, created.text
    supplier_id = created.json()["data"]["id"]

    try:
        listed_as_a = c.get("/api/v1/suppliers", headers=_token(pem, tenant_a)).json()["data"]
        assert supplier_id not in [row["id"] for row in listed_as_a], (
            "tenant A's listing included a supplier created by tenant B"
        )

        fetched_as_a = c.get(f"/api/v1/suppliers/{supplier_id}", headers=_token(pem, tenant_a))
        assert fetched_as_a.status_code == 404, (
            f"tenant A could fetch tenant B's supplier by id: {fetched_as_a.status_code} {fetched_as_a.text}"
        )

        listed_as_b = c.get("/api/v1/suppliers", headers=_token(pem, tenant_b)).json()["data"]
        assert supplier_id in [row["id"] for row in listed_as_b], (
            "tenant B lost visibility of its own row — this would hide a real bug, not just a leak"
        )
    finally:
        purge_tenant(tenant_b)


def test_no_unpinned_sessions_outside_request_cycle():
    """Every non-request DB session must be tenant-pinned.

    `get_session_factory()()` is safe on SQLite (no RLS) and silently broken on
    Postgres: the RLS `WITH CHECK` rejects the write and a broad `except` hides
    it. That is how idempotency replay and the SSE audit both died in production
    while the test suite stayed green. This test makes the mistake impossible to
    reintroduce, because SQLite cannot catch it.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "get_session_factory()()" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        # health.py probes liveness with a read-only SELECT 1 + version check,
        # which is tenant-independent by design. tenant.py *defines* the pinned
        # wrapper, so the raw call there is the one being made safe.
        if rel in {"routers/health.py", "core/tenant.py"}:
            continue
        # Everything else must go through pinned_session().
        for match in re.finditer(r"get_session_factory\(\)\(\)", text):
            line_no = text[: match.start()].count("\n") + 1
            window = text[max(0, match.start() - 400) : match.start()]
            if "pinned_session(" not in window:
                offenders.append(f"{rel}:{line_no}")
    assert not offenders, (
        "unpinned get_session_factory()() outside health.py — RLS will reject "
        f"these writes on Postgres: {offenders}"
    )


def test_pinned_session_pins_on_postgres(monkeypatch):
    """pinned_session must issue SET LOCAL when the dialect is postgres."""
    from app.core import tenant as tenant_mod

    executed: list[str] = []

    class FakeBind:
        class dialect:  # noqa: N801
            name = "postgresql"

    class FakeSession:
        bind = FakeBind()
        info: dict = {}

        def execute(self, stmt, params=None):  # type: ignore[no-untyped-def]
            executed.append(str(stmt))
            return None

    monkeypatch.setattr(tenant_mod, "get_session_factory", lambda: (lambda: FakeSession()))
    tenant_mod.pinned_session("tenant-a")
    assert any("app.tenant_id" in s for s in executed), executed
    # An empty tenant must NOT be pinned — that would set an empty GUC and
    # silently make every RLS predicate false, hiding rows instead of leaking.
    executed.clear()
    tenant_mod.pinned_session("")
    assert not executed
