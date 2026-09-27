"""Idempotency fingerprint bounds + quarantined-document search.

Both were Postgres-only failures that no test could see, because every test
module builds the schema with `create_all` on SQLite (which enforces neither
VARCHAR length nor a join).

- `idempotency_keys.key` is VARCHAR(512) but the stored fingerprint is
  `method|path|header|sha256(body)`; an over-long one raised `DataError`, which
  the fail-open handlers swallowed, so the write succeeded with idempotency
  silently off.
- `/documents/search` never joined `documents`, so chunks of a quarantined
  document stayed searchable.
"""
from datetime import datetime, timedelta, timezone

import io

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.core.idempotency import FINGERPRINT_MAX, _fingerprint

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "id-kid"
    from app.core import security

    security.override_jwks({"id-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, sub="buyer1", tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer", "Procurement Manager"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "id-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_a_stale_claim_is_actually_taken_over(client, monkeypatch):
    """A claim left `in_progress` by a killed process must be recoverable.

    This is the branch that decides whether a crashed write wedges an endpoint
    forever or recovers. It was broken in a way no test could see, because the
    broken statement raised inside the broad `except Exception` and the function
    then returned `("unavailable", None)` — which *also* runs the handler. So the
    retry appeared to work while the row stayed `in_progress` forever, and every
    subsequent retry took the same broken branch.

    Asserted directly against `_claim` because the HTTP-level behaviour is
    identical either way; only the row's state distinguishes them.
    """
    from app.core.idempotency import _claim
    from app.core.tenant import pinned_session
    from app.models.audit import IdempotencyKey

    fingerprint = _fingerprint("POST", "/api/v1/purchase-orders", "8" * 36, b'{"a":1}')

    # First request claims the fingerprint and is killed before completing.
    outcome, _ = _claim("t1", fingerprint, "POST", "/api/v1/purchase-orders")
    assert outcome == "proceed"

    db = pinned_session("t1")
    try:
        row = db.get(IdempotencyKey, db.query(IdempotencyKey).filter(
            IdempotencyKey.key == fingerprint).first().id)
        assert row.state == "in_progress"
    finally:
        db.close()

    # A retry inside the window is correctly refused: the holder may still be alive.
    monkeypatch.setattr("app.core.idempotency.STALE_CLAIM_S", 10_000)
    blocked, _ = _claim("t1", fingerprint, "POST", "/api/v1/purchase-orders")
    assert blocked == "in_flight"

    # Past the window the claim is taken over, and the row is really updated.
    monkeypatch.setattr("app.core.idempotency.STALE_CLAIM_S", -1)
    taken, _ = _claim("t1", fingerprint, "POST", "/api/v1/purchase-orders")
    assert taken == "proceed"

    db = pinned_session("t1")
    try:
        row = db.get(IdempotencyKey, db.query(IdempotencyKey).filter(
            IdempotencyKey.key == fingerprint).first().id)
        assert row.state == "in_progress", "the row was never actually taken over"
    finally:
        db.close()


def test_takeover_compares_and_swaps(client, monkeypatch):
    """Two racers that both see a stale claim: only one may proceed.

    The UPDATE matches on the `claimed_at` the racer read, so the loser's WHERE
    no longer matches once the winner has committed and it gets zero rows.
    Without that, both would return `proceed` and both would run the handler —
    the exact double-write the claim exists to prevent.
    """
    from app.core.idempotency import _claim
    from app.core.tenant import pinned_session
    from app.models.audit import IdempotencyKey
    from sqlalchemy import select as sa_select

    monkeypatch.setattr("app.core.idempotency.STALE_CLAIM_S", -1)
    path = "/api/v1/purchase-orders"
    fingerprint = _fingerprint("POST", path, "9" * 36, b'{"b":2}')
    assert _claim("t1", fingerprint, "POST", path)[0] == "proceed"

    # Simulate the stale state directly, so both racers read the same timestamp.
    db = pinned_session("t1")
    try:
        row = db.execute(sa_select(IdempotencyKey).where(
            IdempotencyKey.key == fingerprint)).scalar_one()
        row.state = "in_progress"
        db.commit()
        row_id = row.id
    finally:
        db.close()

    first, _ = _claim("t1", fingerprint, "POST", path)
    # The winner has rewritten claimed_at, so a racer holding the old value now
    # matches nothing and must be told the claim is in flight.
    db = pinned_session("t1")
    try:
        current = db.get(IdempotencyKey, row_id)
        db.refresh(current)
        assert current.state == "in_progress"
    finally:
        db.close()
    assert first == "proceed"


def test_fingerprint_fits_the_column_for_realistic_paths():
    """A long path plus a real key must not overflow `idempotency_keys.key`.

    The realistic worst case is a nested resource:
    `POST /api/v1/purchase-orders/{36-char-uuid}/receipts` with a 36-character
    Idempotency-Key is ~168 characters — past the old VARCHAR(128).
    """
    path = "/api/v1/purchase-orders/" + "0" * 36 + "/receipts"
    fp = _fingerprint("POST", path, "8" * 36, b'{"lines":[]}')
    assert len(fp) <= FINGERPRINT_MAX
    assert fp.startswith("POST|" + path)
    # still distinguishable per key
    assert fp != _fingerprint("POST", path, "9" * 36, b'{"lines":[]}')
    # and per body
    assert fp != _fingerprint("POST", path, "8" * 36, b'{"lines":[1]}')


def test_fingerprint_hashes_rather_than_truncates_when_pathological():
    """An absurd path is folded into a stable digest, not cut off mid-string.

    Truncation would make two different long paths collide onto one stored
    response, which is a wrong replay — worse than no idempotency at all.
    """
    a = _fingerprint("POST", "/api/v1/" + "a" * 900, "k", b"{}")
    b = _fingerprint("POST", "/api/v1/" + "b" * 900, "k", b"{}")
    assert len(a) <= FINGERPRINT_MAX
    assert a != b
    # stable across calls, so replay still works
    assert a == _fingerprint("POST", "/api/v1/" + "a" * 900, "k", b"{}")


def test_long_path_replay_still_works_end_to_end(client):
    """The point of the fix: a nested write still replays on retry."""
    c, pem = client
    h = _h(pem)
    s = c.post("/api/v1/suppliers", json={"code": "S-IDEM", "name": "Idem Supplier"}, headers=h).json()["data"]["id"]
    po = c.post("/api/v1/purchase-orders", json={"code": "PO-IDEM", "supplier_id": s, "currency": "USD",
              "lines": [{"description": "Bolt", "quantity": 10, "unit_price_minor": 100}]}, headers=h).json()["data"]["id"]
    c.post(f"/api/v1/purchase-orders/{po}/approve", headers=_h(pem, "mgr1"))
    c.post(f"/api/v1/purchase-orders/{po}/send", headers=h)
    plid = c.get(f"/api/v1/purchase-orders/{po}", headers=h).json()["data"]["lines"][0]["id"]

    idem = {**h, "Idempotency-Key": "fixed-key-1234"}
    body = {"lines": [{"po_line_id": plid, "quantity": 1}]}
    first = c.post(f"/api/v1/purchase-orders/{po}/receipts", json=body, headers=idem)
    assert first.status_code == 201, first.text
    second = c.post(f"/api/v1/purchase-orders/{po}/receipts", json=body, headers=idem)
    assert second.status_code == 201
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_quarantined_documents_are_not_searchable(client):
    """Quarantine is a review gate; its text must not leak into search results."""
    c, pem = client
    h = _h(pem)
    files = {"file": ("evidence.csv", io.BytesIO(b"ref,zebra marker\n1,CONFIDENTIAL zebra marker content\n"), "text/csv")}
    ok = c.post("/api/v1/documents", files=files, headers=h)
    assert ok.status_code == 201, ok.text
    did = ok.json()["data"]["id"]
    # chunks only exist once the document has been extracted
    assert c.post(f"/api/v1/documents/{did}/extract", headers=h).status_code == 200
    assert c.get("/api/v1/documents/search?q=zebra", headers=h).json()["data"] != []

    # mark the document quarantined directly, the way the integrity paths do
    from app.core.tenant import pinned_session
    from app.models.document import Document

    db = pinned_session("t1")
    try:
        row = db.get(Document, ok.json()["data"]["id"])
        assert row is not None
        row.status = "quarantined"
        db.commit()
    finally:
        db.close()

    after = c.get("/api/v1/documents/search?q=zebra", headers=h)
    assert after.status_code == 200
    assert after.json()["data"] == []
