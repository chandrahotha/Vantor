"""Canonical audit chain — append, link, verify, detect tampering (sqlite)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.registry import Base
from app.services.audit import record_event, verify_chain


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_chain_links_and_verifies():
    db = _db()
    e1 = record_event(db, tenant_id="t1", actor="u1", action="SUPPLIER_CREATED", resource="supplier", resource_id="s1")
    e2 = record_event(db, tenant_id="t1", actor="u1", action="SUPPLIER_APPROVED", resource="supplier", resource_id="s1")
    assert e1.prev_hash == ""
    assert e2.prev_hash == e1.hash
    ok, msg, _trunc = verify_chain(db, tenant_id="t1")
    assert ok, msg
    db.close()


def test_tamper_breaks_chain():
    db = _db()
    record_event(db, tenant_id="t1", actor="u1", action="PO_CREATED", resource="po", resource_id="p1")
    row = record_event(db, tenant_id="t1", actor="u1", action="PO_APPROVED", resource="po", resource_id="p1")
    row.after = {"tampered": True}  # direct mutation simulates disk-level tamper
    db.flush()
    ok, msg, _trunc = verify_chain(db, tenant_id="t1")
    assert not ok
    assert "mismatch" in msg or "break" in msg
    db.close()


def test_tenants_have_independent_chains():
    db = _db()
    a = record_event(db, tenant_id="ta", actor="u", action="X", resource="r")
    b = record_event(db, tenant_id="tb", actor="u", action="X", resource="r")
    assert a.prev_hash == "" and b.prev_hash == ""
    # Genesis hashes differ because occurred_at is part of the payload (correct:
    # timestamps must affect the chain). Independence = separate prev_hash tails
    # + each tenant verifies on its own.
    ok_a, _, _ = verify_chain(db, tenant_id="ta")
    ok_b, _, _ = verify_chain(db, tenant_id="tb")
    assert ok_a and ok_b
    db.close()


def test_rows_sharing_a_timestamp_still_verify():
    """The regression that made `test_e2e_workflow` fail on a clean checkout.

    `record_event` took the chain tail with `ORDER BY occurred_at DESC, id DESC`
    while `verify_chain` walked `occurred_at ASC, id ASC`. `id` is a random
    `uuid4().hex`, so for any two rows sharing a timestamp the two orderings
    disagreed about half the time, and a chain nobody had touched reported
    itself broken. A single pass of the real procurement workflow produced eight
    such collisions.

    `record_event` no longer emits ties, but rows written before this fix still
    have them, so the rows are built here by hand — correctly chained, sharing
    one timestamp — which is exactly what is sitting in a deployed database.
    A verification that sorts instead of following the links fails this.
    """
    from datetime import datetime, timezone

    from app.models.audit import AuditEvent
    from app.services.audit import _payload_for, compute_hash

    same = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    db = _db()
    prev = ""
    for i in range(12):
        payload = _payload_for(tenant_id="t1", actor="u1", action=f"EVENT_{i}", resource="r",
                               resource_id=str(i), occurred_at=same, ip="", before={}, after={},
                               reason="", approval="", source="api")
        digest = compute_hash(prev, payload)
        db.add(AuditEvent(tenant_id="t1", created_by="u1", updated_by="u1", actor="u1",
                          action=f"EVENT_{i}", resource="r", resource_id=str(i), occurred_at=same,
                          ip="", before={}, after={}, reason="", approval="", source="api",
                          prev_hash=prev, hash=digest))
        prev = digest
    db.flush()

    ok, msg, _trunc = verify_chain(db, tenant_id="t1")
    assert ok, msg
    assert "12 events" in msg
    db.close()


def test_timestamps_are_strictly_increasing_within_a_tenant():
    """What makes the tail lookup a total order, and so the chain verifiable."""
    db = _db()
    stamps = [record_event(db, tenant_id="t1", actor="u", action="E", resource="r").occurred_at
              for _ in range(30)]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == 30, "two events shared a timestamp — the tail lookup is ambiguous again"
    db.close()


def test_a_fork_is_detected():
    """Two rows appended to the same parent — what a lost row lock produces."""
    db = _db()
    first = record_event(db, tenant_id="t1", actor="u", action="A", resource="r")
    second = record_event(db, tenant_id="t1", actor="u", action="B", resource="r")
    third = record_event(db, tenant_id="t1", actor="u", action="C", resource="r")
    # Re-point C at A, so A has two successors.
    third.prev_hash = first.hash
    db.flush()
    ok, msg, _trunc = verify_chain(db, tenant_id="t1")
    assert not ok
    assert "fork" in msg
    assert second.hash != third.hash
    db.close()


def test_a_row_removed_from_the_middle_is_detected():
    """The sorted walk could not see this: deleting a middle row left a shorter
    but internally consistent-looking sequence."""
    db = _db()
    record_event(db, tenant_id="t1", actor="u", action="A", resource="r")
    middle = record_event(db, tenant_id="t1", actor="u", action="B", resource="r")
    record_event(db, tenant_id="t1", actor="u", action="C", resource="r")
    db.delete(middle)
    db.flush()
    ok, msg, _trunc = verify_chain(db, tenant_id="t1")
    assert not ok
    assert "not linked" in msg
    db.close()
