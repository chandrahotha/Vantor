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
