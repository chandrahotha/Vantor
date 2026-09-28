"""Real Postgres + real schema. Skips cleanly when there is none.

The schema-defect tests assert `alembic check` and FKs. They matter only when
run against the migrations on real Postgres; on SQLite the assertions would be
about SQLAlchemy's behaviour, not about the DDL being what it should be.

The `pg_client` fixture lives in `conftest.py`; see `pgsupport.py` for why it
points `DATABASE_URL` and the Alembic config at the same database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

pytestmark = pytest.mark.pg

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


def _h(pem: bytes, sub="u1", tenant="t1", roles=("Buyer", "Procurement Manager")):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)}, "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "pg-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_database_matches_metadata():
    """`alembic check` — metadata matches DDL, no drift.

    Run inside `pointed_at_postgres()` because `alembic/env.py` reads
    `DATABASE_URL` from the environment in preference to the config it is
    handed, and the fast suite sets that to `sqlite://`.

    `build_schema()` is called here rather than left to the `pg_client` fixture.
    This test does not use that fixture, so it was relying on whichever
    PG-backed test happened to run before it to have migrated the database —
    which `pytest-randomly` is free to reorder. On an empty test database
    `alembic check` refuses with "Target database is not up to date" and the
    test reports a schema-drift failure for a schema that was never built.
    """
    from alembic import command

    from pgsupport import build_schema, pg_alembic_config, pointed_at_postgres, require_postgres

    require_postgres()
    with pointed_at_postgres():
        build_schema()
        command.check(pg_alembic_config())


def test_the_models_links_are_exactly_the_migrated_ones():
    """The ORM and the migrations must describe the same set of links.

    They are maintained in two places — `app/models/*.py` declares the
    constraints, `0019_foreign_keys` + `0024_match_run_price_case_links` create
    them — and nothing tied them together. That is how the models came to
    declare 45 single-column `ForeignKey("parent.id")` for a schema that has used
    composite, tenant-carrying references since 0019, and how six real links
    (`match_runs`, `price_cases`) ended up with *no* constraint in the database
    while the ORM claimed otherwise.

    `test_database_matches_metadata` compares the two, but it only runs with a
    reachable Postgres, so it is skipped everywhere the PG tier is unavailable.
    This one needs no database: it compares the ORM's declared constraints
    against the migration source, so the two cannot drift apart unnoticed even
    where the Postgres tier never runs.
    """
    import re

    from pgsupport import BACKEND_ROOT

    from app.models.registry import Base

    # Derived from the package, not from the process CWD: CI runs this test from
    # the repository root, where `Path("alembic/versions")` does not exist and the
    # test fails on a missing file rather than on anything it asserts.
    versions = BACKEND_ROOT / "alembic" / "versions"
    migrations = {
        "0019_foreign_keys": versions / "0019_foreign_keys.py",
        "0024_match_run_price_case_links": versions / "0024_match_run_price_case_links.py",
    }

    declared: set[tuple[str, str, str]] = set()
    for name, path in migrations.items():
        source = path.read_text(encoding="utf-8")
        for child, col, parent in re.findall(r'\("([a-z_]+)", "([a-z_]+)",\s*"([a-z_]+)"\)', source):
            declared.add((child, col, parent))
        assert len(declared) > 0, f"no links parsed out of {name}; the regex is stale"

    modelled: set[tuple[str, str, str]] = set()
    for table_name, table in Base.metadata.tables.items():
        for fkc in table.foreign_key_constraints:
            cols = [c.name for c in fkc.columns]
            # Every link is the composite shape [tenant_id, <col>].
            assert cols[0] == "tenant_id", (
                f"{table_name}: {fkc.name} is not a tenant-carrying link: {cols}")
            target = [e.target_fullname for e in fkc.elements]
            parent = target[0].split(".")[0]
            modelled.add((table_name, cols[1], parent))

    missing = declared - modelled
    extra = modelled - declared
    assert not missing, (
        "the migrations create these links but no model declares them, so the "
        f"ORM would not know about the constraint: {sorted(missing)}")
    assert not extra, (
        "the models declare these links but no migration creates them, so the "
        f"database will not enforce them: {sorted(extra)}")


def test_every_linked_column_should_have_a_foreign_key():
    from app.models.registry import Base

    assert "documents" in Base.metadata.tables
    assert "approvals" in Base.metadata.tables

    # Polymorphic / cross-entity-only references: there is no single target.
    no_fk = {"documents": {"resource_id"},
             "approvals": {"resource_id"},
             "audit_events": {"resource_id"},
             "contract_signatures": {"envelope_id"}}

    for name, table in sorted(Base.metadata.tables.items()):
        composite: set[str] = set()
        for fkc in table.foreign_key_constraints:
            for element in fkc.columns:
                composite.add(element.name)

        for col in table.columns:
            if col.name.endswith("_id") and col.name != "id" and col.name != "tenant_id":
                if name in no_fk and col.name in no_fk[name]:
                    continue
                assert col.foreign_keys or col.name in composite, (
                    f"{name}.{col.name} has no FOREIGN KEY and is not on the "
                    "polymorphic exception list"
                )


def test_invoice_with_cross_po_line_is_rejected(pg_client):
    """In SQLite the bad cross-PO link was silently written. On Postgres the FK says no."""
    c, pem, tenant = pg_client
    h = _h(pem, tenant=tenant)
    sup = c.post("/api/v1/suppliers", json={"code": "S-PG", "name": "PG Supplier"}, headers=h).json()["data"]["id"]
    po1 = c.post("/api/v1/purchase-orders", json={"code": "PO-PG-1", "supplier_id": sup, "currency": "USD",
                                                  "lines": [{"description": "Bolt", "quantity": 1, "unit_price_minor": 10}]},
                 headers=h).json()["data"]["id"]
    po2 = c.post("/api/v1/purchase-orders", json={"code": "PO-PG-2", "supplier_id": sup, "currency": "USD",
                                                  "lines": [{"description": "Nut", "quantity": 1, "unit_price_minor": 10}]},
                 headers=h).json()["data"]["id"]
    l1 = c.get(f"/api/v1/purchase-orders/{po1}", headers=h).json()["data"]["lines"][0]["id"]
    bad = c.post(f"/api/v1/purchase-orders/{po2}/invoices",
                 json={"code": "INV-PG", "lines": [{"po_line_id": l1, "quantity": 1, "unit_price_minor": 10}]},
                 headers=h)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVOICE_LINE_NOT_ON_PO"


def test_a_root_category_can_be_created(pg_client):
    """A create that cannot succeed is not a constraint test, it is an outage.

    `categories.parent_id` is a composite FK to `categories (tenant_id, id)`, so
    "no parent" has to be NULL. The API accepted `""` as its default and wrote
    that literal, which asks Postgres to match a category whose id is the empty
    string. Every root-category create therefore violated the constraint, and
    the handler reported it as `409 Category code exists` — naming a uniqueness
    conflict for an insert that had nothing to do with one, so the failure
    pointed at the wrong thing entirely.

    This is why the test is Postgres-only. SQLite does not enforce foreign keys
    unless it is asked to, so the same call returns 201 there and the 330-test
    default suite is green while the feature is broken on the database the
    product actually runs on.
    """
    c, pem, tenant = pg_client
    h = _h(pem, tenant=tenant)

    root = c.post("/api/v1/catalog/categories",
                  json={"code": "CAT-ROOT", "name": "Root category"}, headers=h)
    assert root.status_code == 201, (
        f"creating a root category failed: {root.status_code} {root.text}")

    root_id = root.json()["data"]["id"]

    # And a child still links to its parent, so the fix did not simply drop the
    # constraint on the floor.
    child = c.post("/api/v1/catalog/categories",
                   json={"code": "CAT-CHILD", "name": "Child category", "parent_id": root_id},
                   headers=h)
    assert child.status_code == 201, child.text

    listed = c.get("/api/v1/catalog/categories", headers=h).json()["data"]
    assert len(listed) == 2, f"expected the root and its child, got {listed}"


def test_a_category_whose_parent_is_in_another_tenant_is_rejected(pg_client):
    """The composite FK is the cross-tenant guard; assert it actually refuses.

    A single-column FK on `parent_id` alone would happily point at another
    tenant's category, and the tree would then contain a row from outside the
    tenant — the same class of leak the composite keys exist to prevent.

    The second tenant is unique per run and removed afterwards. `purge_tenant`
    cleans only the module-scoped fixture tenant, so a fixed name here left rows
    behind and the *second* run of this test failed with `409 Category code
    exists` on its own setup — which reads as the constraint refusing the
    legitimate create rather than as leftover state.
    """
    import uuid

    from tests.pgsupport import purge_tenant

    c, pem, tenant = pg_client
    h = _h(pem, tenant=tenant)
    other_tenant = f"other-{uuid.uuid4().hex[:12]}"
    other = _h(pem, sub="u2", tenant=other_tenant)

    try:
        foreign = c.post("/api/v1/catalog/categories",
                         json={"code": "CAT-FOREIGN", "name": "Someone else's"},
                         headers=other)
        assert foreign.status_code == 201, foreign.text
        foreign_id = foreign.json()["data"]["id"]

        child = c.post("/api/v1/catalog/categories",
                       json={"code": "CAT-BORROWED", "name": "Borrowed parent",
                             "parent_id": foreign_id}, headers=h)
        # The refusal may come from either layer, and both are wanted:
        # `require_no_cycle` checks that the parent exists *within this tenant's*
        # scope and answers 422, and the composite FK refuses the same row with a
        # constraint violation if it ever reaches the database. Asserting one
        # specific code would have pinned the test to whichever layer happens to
        # run first, and would have called the other a missing control.
        assert child.status_code in (409, 422), (
            "a category was parented to a row in another tenant; neither the "
            f"application check nor the composite FK refused it: "
            f"{child.status_code} {child.text}")
        assert child.json()["error"]["code"] in ("CONFLICT", "REFERENCE_CYCLE")

        # And nothing was written: the refusal is a refusal, not a warning.
        # Asserted by the absence of the row this test tried to create, not by
        # the full listing, so it holds whether or not another test in this
        # module has already put categories in the same tenant.
        listed = c.get("/api/v1/catalog/categories", headers=h).json()["data"]
        assert "CAT-BORROWED" not in [x["code"] for x in listed], (
            f"a cross-tenant parent was accepted anyway: {listed}")
    finally:
        purge_tenant(other_tenant)
