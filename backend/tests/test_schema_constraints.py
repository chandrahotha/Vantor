"""The migration and the models must agree on every domain constraint.

`alembic check` compares rendered DDL, but it only runs in CI against a live
PostgreSQL and only catches *drift* — it will happily accept two different
CHECK predicates that both happen to exist nowhere else. A constraint edited in
`models/purchase.py` and forgotten in the migration is invisible until the
database and the ORM disagree at runtime.

This test is the cheap guard: it reads both sides and asserts they are the same
set, by name and by predicate. It needs no database, so it runs in the fast tier.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _load_migration(name: str):
    path = BACKEND / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration("0020_domain_constraints")


def _all_migration_checks() -> dict[tuple[str, str], str]:
    """Every CHECK created by *any* migration, not just 0020.

    This fixture originally read 0020 alone, which was correct when 0020 was the
    only migration adding CHECKs. The moment a second migration added one — 0021
    for `verified_via` — the "is every model CHECK migrated?" assertion failed on
    a constraint that *was* migrated, because the test had a hardcoded view of
    which migrations exist. A guard that only knows about the constraint migration
    that motivated it stops guarding as soon as the schema grows.

    Obtained by *running* each migration's `upgrade()` against a recording stand-in
    for alembic's `op`, rather than by reading the source. Two source-reading
    approaches were tried first and both were wrong: scanning for "any list of
    3-tuples" swept in 0019's foreign-key table (also `(table, column, target)`
    triples, 38 phantom checks), and resolving loop variables through the AST found
    nothing, because both 0020 and 0021 declare their checks inside
    `for table, name, predicate in CHECKS:` loops.

    Executing `upgrade()` is what an alembic run does anyway, so the recorder sees
    exactly the constraints a real migration would create — and a migration that
    would crash under a real `op` fails here loudly rather than being silently
    skipped.
    """
    import importlib.util

    class _EmptyResult:
        """A result set with no rows, so a preflight check finds nothing to
        complain about and the migration proceeds to the DDL this test wants."""

        def mappings(self) -> list:
            return []

        def scalar_one_or_none(self):  # type: ignore[no-untyped-def]
            return None

    class _FakeBind:
        def execute(self, *_a, **_k) -> _EmptyResult:  # type: ignore[no-untyped-def]
            return _EmptyResult()

    class RecordingOp:
        """Stands in for `alembic.op`, recording the constraints it is asked for."""

        def __init__(self) -> None:
            self.checks: list[tuple[str, str, str]] = []

        def create_check_constraint(self, name, table, predicate, **kw):  # type: ignore[no-untyped-def]
            self.checks.append((name, table, str(predicate)))

        def get_bind(self) -> _FakeBind:  # type: ignore[no-untyped-def]
            # 0020 runs a data preflight before its DDL. Without a bind it
            # would raise on `None.execute(...)` and the test would report a
            # broken migration for a missing test double.
            return _FakeBind()

        def __getattr__(self, _item):  # type: ignore[no-untyped-def]
            # Everything else a migration may do (add_column, create_index,
            # execute, alter_column) is irrelevant here and must not explode.
            return lambda *a, **k: None

    out: dict[tuple[str, str], str] = {}
    versions = BACKEND / "alembic" / "versions"
    for path in sorted(versions.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if not (spec and spec.loader):
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            continue
        recorder = RecordingOp()
        module.op = recorder  # type: ignore[attr-defined]
        upgrade = getattr(module, "upgrade", None)
        if not callable(upgrade):
            continue
        try:
            upgrade()
        except Exception as exc:
            raise AssertionError(
                f"{path.name}: upgrade() failed against the recording op ({exc!r}). "
                "A migration that cannot run is a broken migration."
            ) from exc
        for name, table, predicate in recorder.checks:
            out[(table, name)] = predicate
    return out


@pytest.fixture(scope="module")
def all_migration_checks() -> dict[tuple[str, str], str]:
    return _all_migration_checks()


@pytest.fixture(scope="module")
def model_checks() -> dict[tuple[str, str], str]:
    """Every CHECK constraint declared on an ORM table: (table, name) -> SQL."""
    from app.models.registry import Base

    out: dict[tuple[str, str], str] = {}
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.__class__.__name__ != "CheckConstraint":
                continue
            sqltext = str(constraint.sqltext)
            out[(table.name, constraint.name)] = sqltext
    return out


@pytest.fixture(scope="module")
def model_uniques() -> set[tuple[str, str]]:
    """Plain (non-partial) unique constraints, and unique indexes."""
    from app.models.registry import Base

    out: set[tuple[str, str]] = set()
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.__class__.__name__ not in (
                "UniqueConstraint",
                "UniqueConstraintColumnList",
            ):
                continue
            out.add((table.name, constraint.name or ""))
        for index in table.indexes:
            if index.unique:
                out.add((table.name, index.name or ""))
    return out


def _norm_where(sql) -> str | None:
    """Normalise a partial-index predicate for comparison.

    Alembic and the ORM build the same clause from the same string here, but
    whitespace and quoting differ between the two renderers, so a byte comparison
    would report drift that does not exist and train people to ignore this test.
    """
    if sql is None:
        return None
    text = " ".join(str(sql).split())
    return text.replace('"', "").replace("'", "'") or None


def test_every_migrated_check_exists_on_the_model(migration, model_checks):
    missing = [(table, name) for table, name, _predicate in migration.CHECKS
               if (table, name) not in model_checks]
    assert not missing, (
        "0020 adds CHECK constraints the models do not declare — `alembic check` "
        f"will report drift: {missing}")

def test_every_migrated_check_has_identical_predicate(migration, model_checks):
    mismatched = [
        {"table": table, "name": name,
         "migration": predicate, "model": model_checks.get((table, name))}
        for table, name, predicate in migration.CHECKS
        if (table, name) in model_checks and model_checks[(table, name)] != predicate
    ]
    assert not mismatched, f"CHECK predicate drift between migration and model: {mismatched}"


def test_every_model_check_is_migrated(model_checks, all_migration_checks):
    """A CHECK added to a model and not to a migration is the dangerous direction."""
    unmigrated = sorted(set(model_checks) - set(all_migration_checks))
    assert not unmigrated, (
        "the models declare CHECK constraints that no migration creates — the "
        f"database will not have them: {unmigrated}")


def test_every_migration_check_is_declared_on_a_model(all_migration_checks, model_checks):
    """The other direction: a CHECK in a migration that the model does not declare.

    This is what `alembic check` catches, but only against a live database, so it
    is asserted here where it runs on every push.
    """
    undeclared = sorted(set(all_migration_checks) - set(model_checks))
    assert not undeclared, (
        "migrations create CHECK constraints the models do not declare: "
        f"{undeclared}")


def test_migration_check_predicates_match_the_models(all_migration_checks, model_checks):
    mismatched = [
        {"table": table, "name": name,
         "migration": predicate, "model": model_checks.get((table, name))}
        for (table, name), predicate in all_migration_checks.items()
        if (table, name) in model_checks and model_checks[(table, name)] != predicate
    ]
    assert not mismatched, f"CHECK predicate drift between migration and model: {mismatched}"


def test_every_migrated_unique_exists_on_the_model(migration, model_uniques):
    missing = [(t, n) for t, n, _cols, _where in migration.UNIQUES
               if (t, n) not in model_uniques]
    assert not missing, f"0020 adds unique constraints the models do not declare: {missing}"


def test_partial_unique_predicates_match_the_models(migration):
    """The WHERE clause is the whole point of the partial indexes.

    A partial unique index in the migration and a plain unique constraint on the
    model is a drift `alembic check` may not flag, and the failure it causes is
    baffling rather than loud: the database refuses the second internal signature
    in a tenant, with an error naming an envelope that does not exist.
    """
    from app.models.registry import Base

    declared: dict[tuple[str, str], str | None] = {}
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            if index.unique:
                declared[(table.name, index.name or "")] = _norm_where(
                    index.dialect_options["postgresql"].get("where")
                )

    mismatched = [
        {"table": table, "name": name,
         "migration": where,
         "model": declared.get((table, name), "<index not declared>")}
        for table, name, _cols, where in migration.UNIQUES
        if where is not None
        and _norm_where(where) != declared.get((table, name), "<missing>")
    ]
    assert not mismatched, (
        f"partial unique index predicate drift between migration and model: {mismatched}")


def test_only_the_signature_index_is_partial(migration):
    """A partial index that should be plain is a silent hole.

    The migration's business keys are plain unique constraints except for the
    e-sign envelope index, whose predicate is load-bearing. If a future edit
    makes one of the others partial, the constraint stops covering rows and the
    preflight will not notice.
    """
    partial = sorted(name for _t, name, _c, where in migration.UNIQUES if where)
    assert partial == ["uq_sig_tenant_provider_envelope"], (
        f"unexpected partial unique indexes: {partial}")


def test_signature_envelope_index_is_partial(migration):
    """Guards the specific regression this migration had.

    `provider` and `envelope_id` default to `""`, so internal signatures all share
    the same (tenant, '', '') key. A non-partial unique index makes the second
    internal signature of a contract impossible, and a contract legitimately has
    more than one signer.
    """
    from app.models.catalog import ContractSignature

    index = next(i for i in ContractSignature.__table__.indexes
                 if i.name == "uq_sig_tenant_provider_envelope")
    assert index.unique
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, (
        "uq_sig_tenant_provider_envelope must be partial (WHERE method = 'esign'); "
        "a plain unique constraint rejects the second internal signature in a tenant")
    assert "esign" in str(where)


def test_idempotency_claim_columns_are_migrated(migration):
    """VNT-006: the model has claim state; the migration must add it."""
    from app.models.audit import IdempotencyKey

    assert {"state", "claimed_at"} <= set(IdempotencyKey.__table__.columns.keys())
    source = (BACKEND / "alembic" / "versions" / "0020_domain_constraints.py").read_text(encoding="utf-8")
    assert 'add_column("idempotency_keys", sa.Column("state"' in source
    assert 'add_column("idempotency_keys", sa.Column("claimed_at"' in source


def test_status_sets_are_load_behavior(migration):
    """The status sets must be the ones the CHECK constraints were built from.

    They used to be decorative literals that nothing imported, which is how the
    database could hold a status the API would never produce.
    """
    from app.models.purchase import (APPROVAL_STATUSES, INVOICE_STATUSES,
                                     PO_STATUSES, REQ_STATUSES)

    def rendered(values: set[str]) -> str:
        return "in (" + ", ".join(f"'{v}'" for v in sorted(values)) + ")"

    for values, table, column in (
        (REQ_STATUSES, "requisitions", "status"),
        (PO_STATUSES, "purchase_orders", "status"),
        (INVOICE_STATUSES, "invoices", "status"),
        (APPROVAL_STATUSES, "approvals", "status"),
    ):
        expected = f"{column} {rendered(values)}"
        assert any(name == f"ck_{table.rstrip('s')}_status" or expected == pred
                   for t, name, pred in migration.CHECKS
                   if t == table and pred == expected), (
            f"{table}.{column} CHECK does not match the {values} set")
