"""B-07 — the budget ceiling, proven under real concurrency.

`check_budget` is a read-modify-decide: read the locked budget row, SUM the
commitment ledger, compare against the ceiling. Under READ COMMITTED two
approvals in the same category could both read the same `committed`, both pass,
and leave the category over its ceiling — the one control whose entire job is to
make that impossible.

The fix is `SELECT ... FOR UPDATE` on the budget row, held to commit. On SQLite
`with_for_update()` renders to nothing, so a unit test there would pass whether or
not the lock exists: it would be testing SQLAlchemy, not the guarantee. This file
therefore requires real PostgreSQL and skips honestly without it.

What is proven, once `PG_TEST_DATABASE_URL` is set (CI does set it):

- two genuinely concurrent transactions committing in the same (category, period)
  cannot both clear a ceiling that only one of them fits under;
- the loser sees the winner's committed figure, not a stale one;
- the ledger is left consistent: one commitment, total within the ceiling, and
  the losing transaction rolled back clean.

What is NOT proven here: anything about the HTTP layer under real network
concurrency (this drives the session layer directly, which is where the lock
lives), and behaviour on SQLite, which has no row locks at all.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import jwt
import pytest

pytestmark = pytest.mark.pg

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


def _h(pem: bytes, tenant: str, roles=("Buyer", "Procurement Manager", "Admin")) -> dict:
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)}, "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "pg-kid"})
    return {"Authorization": f"Bearer {tok}"}


def _po(c, h, supplier_id: str, category_id: str, code: str, total_minor: int) -> str:
    r = c.post("/api/v1/purchase-orders",
               json={"code": code, "supplier_id": supplier_id, "currency": "USD",
                     "category_id": category_id,
                     "lines": [{"description": "Line", "quantity": 1, "unit_price_minor": total_minor}]},
               headers=h)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _scenario(c, h, ceiling_minor: int) -> tuple[str, str, str]:
    """A category with a budget, and two POs each of which fits alone but not
    together. Returns (category_id, po_a, po_b).

    The codes are suffixed with a per-call counter rather than fixed. The
    `pg_client` fixture is module-scoped: one tenant is generated per module and
    purged only at the end, so every test in this file shares it. Fixed codes
    made the second test in the file collide with the first on
    `uq_cat_tenant_code` and fail with `409 Category code exists` — a collision
    with a *previous test's fixture*, reported against the assertion, which
    reads like the budget ceiling rejecting the second approval.
    """
    from app.routers.catalog import current_period

    _scenario.n += 1
    n = _scenario.n
    cat = c.post("/api/v1/catalog/categories",
                 json={"code": f"CAT-CONC-{n}", "name": f"Concurrency {n}"}, headers=h)
    assert cat.status_code == 201, cat.text
    category_id = cat.json()["data"]["id"]

    sup = c.post("/api/v1/suppliers",
                 json={"code": f"S-CONC-{n}", "name": f"Concurrency Supplier {n}"}, headers=h)
    assert sup.status_code == 201, sup.text
    supplier_id = sup.json()["data"]["id"]

    bud = c.post("/api/v1/budgets",
                 json={"category_id": category_id, "period": current_period(), "ceiling_minor": ceiling_minor},
                 headers=h)
    assert bud.status_code == 201, bud.text

    # Each PO is 60% of the ceiling: both fit individually, neither pair fits.
    each = (ceiling_minor * 60) // 100
    return category_id, _po(c, h, supplier_id, category_id, f"PO-CONC-{n}-A", each), \
        _po(c, h, supplier_id, category_id, f"PO-CONC-{n}-B", each)


_scenario.n = 0


def _commit_like_approval(tenant: str, po_id: str, category_id: str, total: int, barrier: threading.Barrier):
    """One transaction's worth of "approve and commit the money".

    Mirrors `POST /purchase-orders/{id}/approve`: the PO is moved to `approved`
    (which is what puts it inside the ledger SUM), a commitment row is written,
    and the transaction commits. `check_budget` runs in the middle, exactly where
    the route calls it.
    """
    from fastapi import HTTPException
    from sqlalchemy import select, text

    from app.core.tenant import pinned_session
    from app.models.purchase import PurchaseOrder
    from app.models.spend import SpendTransaction
    from app.routers.catalog import check_budget

    db = pinned_session(tenant)
    try:
        po = db.execute(
            select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant, PurchaseOrder.id == po_id)
            .with_for_update()
        ).scalar_one()
        # Both threads reach the decision at the same moment, so without the
        # budget row lock they read the same `committed` and both pass.
        barrier.wait(timeout=10)
        outcome: dict[str, object] = {}
        try:
            outcome["budget"] = check_budget(
                db, tenant_id=tenant, category_id=category_id, this_total=total, currency="USD"
            )
        except HTTPException as exc:
            outcome["error"] = exc
            db.rollback()
            return outcome

        po.status = "approved"
        db.add(SpendTransaction(tenant_id=tenant, created_by="u1", updated_by="u1",
                                kind="commitment", po_id=po.id, currency="USD", amount_minor=total))
        # Touch the locked row so the lock is a real write, as the route does.
        db.execute(text("SELECT pg_sleep(0)"))
        db.commit()
        outcome["ok"] = True
        return outcome
    finally:
        db.close()


def test_two_concurrent_approvals_cannot_both_clear_the_ceiling(pg_client):
    c, pem, tenant = pg_client
    h = _h(pem, tenant)
    ceiling = 100_00
    category_id, po_a, po_b = _scenario(c, h, ceiling)

    barrier = threading.Barrier(2)
    results: list[dict] = []
    lock = threading.Lock()

    def run(po_id: str, total: int) -> None:
        outcome = _commit_like_approval(tenant, po_id, category_id, total, barrier)
        with lock:
            results.append(outcome)

    ta = threading.Thread(target=run, args=(po_a, (ceiling * 60) // 100))
    tb = threading.Thread(target=run, args=(po_b, (ceiling * 60) // 100))
    ta.start()
    tb.start()
    ta.join(timeout=30)
    tb.join(timeout=30)

    assert len(results) == 2, f"a thread did not finish: {results}"

    refused = [r for r in results if "error" in r]
    accepted = [r for r in results if r.get("ok")]
    assert len(refused) == 1, f"expected exactly one refusal, got {results}"
    assert len(accepted) == 1, f"expected exactly one success, got {results}"

    exc = refused[0]["error"]
    assert exc.status_code == 422
    assert exc.detail["code"] == "BUDGET_EXCEEDED"
    # The winner must not have been rejected, and the loser must have seen the
    # winner's figure rather than a stale zero.
    assert int(exc.detail["details"]["committed"]) > 0

    # Ledger consistency: exactly one commitment landed, and the total is inside
    # the ceiling the loser was protecting.
    from sqlalchemy import func, select

    from app.core.tenant import pinned_session
    from app.models.purchase import PurchaseOrder
    from app.models.spend import SpendTransaction

    db = pinned_session(tenant)
    try:
        total = db.execute(
            select(func.coalesce(func.sum(SpendTransaction.amount_minor), 0)).where(
                SpendTransaction.tenant_id == tenant, SpendTransaction.kind == "commitment"
            )
        ).scalar()
        rows = db.execute(
            select(PurchaseOrder.status).where(PurchaseOrder.tenant_id == tenant)
        ).scalars().all()
    finally:
        db.close()

    assert total == (ceiling * 60) // 100
    assert total <= ceiling
    assert sorted(rows) == ["approved", "draft"]


def test_the_loser_sees_the_winners_committed_figure(pg_client):
    """Same guard, asserted from the other side: the refusal's `details`
    must quote the winner's real total, proving the sum was re-read after the
    lock was released rather than computed from the pre-lock snapshot."""
    c, pem, tenant = pg_client
    h = _h(pem, tenant)
    ceiling = 100_00
    category_id, po_a, po_b = _scenario(c, h, ceiling)

    barrier = threading.Barrier(2)
    results: list[dict] = []
    lock = threading.Lock()

    def run(po_id: str, total: int) -> None:
        outcome = _commit_like_approval(tenant, po_id, category_id, total, barrier)
        with lock:
            results.append(outcome)

    # Both threads are started *before* either is joined. A `Barrier(2)` cannot
    # be satisfied by one thread, so starting the first and immediately joining
    # it — which is what this loop did — made the first thread block at the
    # barrier until it timed out and raised `BrokenBarrierError`. The exception
    # escaped the thread target, nothing was appended to `results`, and the test
    # failed with an empty list that said nothing about the budget ceiling.
    threads = [threading.Thread(target=run, args=(po, total))
               for po, total in ((po_a, (ceiling * 60) // 100), (po_b, (ceiling * 60) // 100))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2, f"a thread did not finish: {results}"

    refused = [r for r in results if "error" in r]
    assert len(refused) == 1
    details = refused[0]["error"].detail["details"]
    assert details["committed"] == (ceiling * 60) // 100
    assert details["this"] == (ceiling * 60) // 100
    assert details["ceiling"] == ceiling
    assert details["committed"] + details["this"] > details["ceiling"]


def test_a_category_with_no_budget_row_is_not_gated(pg_client):
    """The other half of the contract: a missing budget is `checked: False`,
    not a silent allow with an invented number attached."""
    from app.core.tenant import pinned_session
    from app.routers.catalog import check_budget

    tenant = pg_client[2]
    db = pinned_session(tenant)
    try:
        assert check_budget(db, tenant_id=tenant, category_id="does-not-exist",
                            this_total=10**9) == {"checked": False}
    finally:
        db.close()
