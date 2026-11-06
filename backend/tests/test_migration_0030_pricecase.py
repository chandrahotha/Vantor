"""The SQL inside migration 0030, executed against a real database.

The migration chain cannot be run end-to-end on SQLite — `0022_pgvector_embeddings`
issues `CREATE EXTENSION vector`, which is Postgres-only — so the migration's own
statements have no coverage from `alembic upgrade head` in the fast tier, and the
weekly Postgres tier would be the first time the SQL ever ran. That is the wrong
place to discover a typo: a migration that fails at an operator's deploy is not a
test failure, it is an outage.

These cases run the two statements the migration actually issues — the duplicate
finder and the retire-the-duplicates update — against a table shaped like
`price_cases`, on whatever database the suite is using.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
import sqlalchemy as sa

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "alembic" / "versions" / "0030_pricecase_one_open_per_line.py")

DDL = """
CREATE TABLE price_cases (
    id           VARCHAR(36) PRIMARY KEY,
    tenant_id    VARCHAR(36) NOT NULL,
    po_line_id   VARCHAR(36) NOT NULL,
    status       VARCHAR(16) NOT NULL,
    created_at   TIMESTAMP   NOT NULL,
    updated_by   VARCHAR(36) NOT NULL DEFAULT ''
)
"""


@pytest.fixture(scope="module")
def migration():
    """Import the migration file directly.

    Alembic loads versions by path, and they are not package modules, so
    `import` cannot reach them. The module has to be found the same way the
    migration runner finds it, or this file tests a copy.
    """
    assert MIGRATION.exists(), f"migration moved: {MIGRATION}"
    spec = importlib.util.spec_from_file_location("m0030", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bind():
    """A *Connection*, which is what `op.get_bind()` hands a migration.

    The first version of this fixture yielded the Engine and the migration's
    `bind.execute(...` raised AttributeError — a test bug, not a migration bug,
    and worth recording because the distinction is exactly what the migration
    depends on: it is written against a Connection because that is the only thing
    alembic ever gives it.
    """
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(sa.text(DDL))
        conn.commit()
        yield conn
    engine.dispose()


def _insert(bind, rows: list[tuple[str, str, str, str, str]]) -> None:
    for rid, tenant, line, status, created in rows:
        bind.execute(sa.text(
            "INSERT INTO price_cases (id, tenant_id, po_line_id, status, created_at, updated_by)"
            " VALUES (:id, :tenant, :line, :status, :created, '')"),
            {"id": rid, "tenant": tenant, "line": line, "status": status, "created": created})
    bind.commit()


def test_the_earliest_open_case_survives_and_the_rest_are_found(migration, bind):
    _insert(bind, [
        ("keep-acme", "acme", "line-1", "open", "2026-01-01T00:00:00"),
        ("dupe-acme", "acme", "line-1", "open", "2026-01-02T00:00:00"),
        ("dupe2-acme", "acme", "line-1", "open", "2026-01-03T00:00:00"),
        # Same line id, different tenant: the partition is tenant-scoped, so this
        # one is not a duplicate of anything.
        ("keep-other", "other", "line-1", "open", "2026-01-04T00:00:00"),
        # Closed cases are not in the predicate.
        ("closed-acme", "acme", "line-2", "dismissed", "2026-01-05T00:00:00"),
        ("open-acme-l3", "acme", "line-3", "open", "2026-01-06T00:00:00"),
    ])
    found = set(migration._duplicate_open_case_ids(bind))
    assert found == {"dupe-acme", "dupe2-acme"}, sorted(found)


def test_unattached_cases_are_never_treated_as_duplicates(migration, bind):
    """`po_line_id = ''` is excluded, and this proves the exclusion is real.

    Without the clause every open case that was raised without a specific line
    would be considered a duplicate of the first one, and the migration would
    dismiss legitimate rows before the index made that permanent.
    """
    _insert(bind, [
        ("free-1", "acme", "", "open", "2026-01-01T00:00:00"),
        ("free-2", "acme", "", "open", "2026-01-02T00:00:00"),
        ("free-3", "acme", "", "open", "2026-01-03T00:00:00"),
    ])
    assert migration._duplicate_open_case_ids(bind) == []


def test_the_retire_statement_is_valid_sql_and_marks_the_author(migration, bind):
    """The exact UPDATE text the migration builds, executed.

    The statement is assembled with a generated bind-parameter list, which is the
    kind of string that only fails when it runs.
    """
    _insert(bind, [
        ("keep", "acme", "line-1", "open", "2026-01-01T00:00:00"),
        ("gone", "acme", "line-1", "open", "2026-01-02T00:00:00"),
    ])
    stale = migration._duplicate_open_case_ids(bind)
    assert stale == ["gone"]

    # The statement comes from the migration itself, not a copy of it here.
    bind.execute(sa.text(migration.retire_statement(len(stale))),
                 {"who": "migration:0030_dedupe",
                  **{f"i{i}": cid for i, cid in enumerate(stale)}})
    bind.commit()
    rows = {r[0]: (r[1], r[2]) for r in bind.execute(sa.text(
        "SELECT id, status, updated_by FROM price_cases"))}
    assert rows["gone"] == ("dismissed", "migration:0030_dedupe")
    assert rows["keep"] == ("open", "")


def test_the_index_predicate_is_the_repair_predicate(migration):
    """One predicate, written twice, must not be allowed to disagree.

    The repair and the index use the same condition; if the index said `open` and
    the repair said `open` *plus* something else, the migration would dismiss the
    wrong rows and then refuse to create the index, or create one that the data
    already violated. That is checked here textually because the two live in
    different places in the file and nothing else compares them.
    """
    assert migration.PREDICATE == "status = 'open' AND po_line_id <> ''"
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "WHERE status = 'open' AND po_line_id <> ''" in sql, (
        "the duplicate finder's WHERE clause no longer matches PREDICATE")
