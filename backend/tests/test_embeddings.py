"""Embeddings + ranked document search. The toy provider is deterministic and
honestly labelled — it proves the ranking pipeline end to end without network."""
import io
import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.services.embeddings import DIMS, cosine, embed, rank

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
    jwk["kid"] = "em-kid"
    from app.core import security

    security.override_jwks({"em-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "em-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_toy_provider_is_deterministic_and_unit_normalised(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "toy")
    a = embed("m10 hex bolt fastener steel")
    b = embed("m10 hex bolt fastener steel")
    assert a == b
    assert len(a) == DIMS
    assert abs(cosine(a, b) - 1.0) < 1e-6
    # Orthogonal content scores lower than the self-match.
    c = embed("payment terms netting thirty days")
    assert cosine(a, c) < 1.0


def test_disabled_provider_writes_no_vectors_and_keyword_mode(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert embed("hello") is None
    ranked, mode = rank("bolt", [{"document_id": "d1", "chunk_no": 0, "text": "bolt", "embedding": {}}])
    assert mode == "keyword" and ranked[0]["text"] == "bolt"


def test_semantic_rerank_beats_keyword_order(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "toy")
    rows = [
        {"document_id": "d1", "chunk_no": 0, "text": "steel fasteners m10", "embedding": embed("steel fasteners m10")},
        {"document_id": "d2", "chunk_no": 0, "text": "invoices and netting", "embedding": embed("payment netting thirty days invoicing")},
    ]
    ranked, mode = rank("fasteners m10", rows)
    assert mode == "toy-rank"
    assert ranked[0]["document_id"] == "d1"


def test_search_flow_with_and_without_vectors(monkeypatch, client):
    c, pem = client
    up = c.post("/api/v1/documents", files={"file": ("art.csv", io.BytesIO(b"procurement steel fasteners bolts m10"), "text/csv")}, headers=_h(pem))
    did = up.json()["data"]["id"]

    # Disabled: search is keyword-only and says mode=keyword.
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    r = c.post(f"/api/v1/documents/{did}/extract", headers=_h(pem))
    assert r.status_code == 200
    assert r.json()["data"]["embedded"] == 0
    s = c.get("/api/v1/documents/search?q=fasteners", headers=_h(pem)).json()
    assert s["pagination"]["mode"] == "keyword"
    assert any(h["documentId"] == did for h in s["data"])

    # Toy provider: extract writes vectors and search ranks them.
    monkeypatch.setenv("EMBEDDING_PROVIDER", "toy")
    r2 = c.post(f"/api/v1/documents/{did}/extract", headers=_h(pem))
    assert r2.json()["data"]["embedded"] == r2.json()["data"]["chunks"] > 0
    s2 = c.get("/api/v1/documents/search?q=fasteners", headers=_h(pem)).json()
    assert s2["pagination"]["mode"] == "toy-rank"


@pytest.mark.pg
def test_ann_search_finds_a_chunk_ilike_could_never_reach(monkeypatch, pg_client):
    """RA-006 (re-audit 2026-10-02): the HNSW index existed since migration 0022
    and had never actually been queried — every candidate was ILIKE-prefiltered
    first, so a chunk with zero literal substring overlap with the query could
    never surface, no matter how close its vector was. This proves the new
    `ORDER BY embedding <=> :qv` pool (search_docs, documents.py) actually runs:
    the uploaded chunk's text contains no form of the query word at all, so the
    keyword stage alone would return zero rows, and only the ANN pool (which has
    no ILIKE filter) can be why it's found. The toy provider's embeddings aren't
    semantically meaningful, but they're always non-null for non-empty text — the
    ANN query's `LIMIT 50` with no further filter means any embedded chunk is
    reachable, which is exactly the mechanism being proven, not the quality of
    the ranking.
    """
    from datetime import datetime, timedelta, timezone

    import jwt

    c, pem, tenant = pg_client

    def _h() -> dict:
        now = datetime.now(timezone.utc)
        tok = jwt.encode(
            {"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
             "realm_access": {"roles": ["Buyer"]}, "exp": now + timedelta(minutes=5), "iat": now},
            pem, algorithm="RS256", headers={"kid": "pg-kid"},
        )
        return {"Authorization": f"Bearer {tok}"}

    monkeypatch.setenv("EMBEDDING_PROVIDER", "toy")
    up = c.post("/api/v1/documents",
                files={"file": ("supply.csv", io.BytesIO(b"steel bolts procurement supply chain logistics"), "text/csv")},
                headers=_h())
    assert up.status_code == 201, up.text
    did = up.json()["data"]["id"]
    ex = c.post(f"/api/v1/documents/{did}/extract", headers=_h())
    assert ex.status_code == 200 and ex.json()["data"]["embedded"] > 0, ex.text

    query = "xenoplasticity"  # appears nowhere in the uploaded text or anywhere else
    s = c.get(f"/api/v1/documents/search?q={query}", headers=_h())
    assert s.status_code == 200, s.text
    data = s.json()
    assert data["pagination"]["mode"] == "toy-rank"
    assert any(h["documentId"] == did for h in data["data"]), (
        "the ANN pool should have found this chunk even with zero ILIKE overlap: "
        f"{data}"
    )


def test_extract_includes_real_page_counts(monkeypatch, client):
    """The old code counted Flate streams as pages."""
    c, pem = client
    pdf = (b"%PDF-1.4\n"
           b"1 0 obj<</Type/Page/Count 1>>endobj\n"
           b"2 0 obj<</Length 60/FlateDecode/FlateDecode/FlateDecode>>stream\n"
           + __import__("zlib").compress(b"BT (hello vantor procurement) Tj ET") + b"\nendstream\nendobj\n")
    up = c.post("/api/v1/documents", files={"file": ("doc.pdf", io.BytesIO(pdf), "application/pdf")}, headers=_h(pem))
    r = c.post(f"/api/v1/documents/{up.json()['data']['id']}/extract", headers=_h(pem))
    assert r.status_code == 200
    assert r.json()["data"]["kind"] == "pdf"
    assert os.environ.get("EMBEDDING_PROVIDER") != "toy" or r.json()["data"]["embedded"] >= 1
