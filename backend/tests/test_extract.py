"""Extraction tests — real parsers, honest quarantine, chunk + search E2E."""
import io
import zipfile
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.services.extract import chunk_text, extract

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


def _pdf_hello() -> bytes:
    import zlib

    content = b"BT /F1 12 Tf 72 720 Td (Hello Vantor world) Tj ET"
    stream = b"<< /Length " + str(len(zlib.compress(content))).encode() + b" /Filter /FlateDecode >>\nstream\n" + zlib.compress(content) + b"\nendstream"
    return b"%PDF-1.4\n1 0 obj\n" + stream + b"\nendobj\ntrailer\n<<>>\n"


def _docx_hello() -> bytes:
    buf = io.BytesIO()
    doc = b'<?xml version="1.0"?><w:document xmlns:w="http://x"><w:body><w:p><w:r><w:t>Quote total five thousand</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def test_pdf_docx_csv_text():
    assert "Hello Vantor" in extract("q.pdf", _pdf_hello()).text
    assert "five thousand" in extract("q.docx", _docx_hello()).text
    assert extract("a.csv", b"sku,qty\nA1,10\n").kind == "text"
    scanned = extract("scan.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert scanned.scanned is True
    import pytest as _pt

    with _pt.raises(Exception):
        extract("evil.exe", b"MZ")
    with _pt.raises(Exception):
        extract("fake.pdf", b"not a pdf at all")


def test_chunk_windows():
    chunks = chunk_text(" ".join(f"w{i}" for i in range(1000)), size=100, overlap=10)
    assert chunks[0].split()[0] == "w0" and chunks[1].split()[0] == "w90"
    assert chunk_text("   ") == []
    import pytest as _pt

    with _pt.raises(Exception):
        chunk_text("hello world", size=50, overlap=50)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
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
    jwk["kid"] = "ex-kid"
    from app.core import security

    security.override_jwks({"ex-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ex-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_extract_search_flow(client):
    c, pem = client
    h = _h(pem, "acme")
    up = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(_pdf_hello()), "application/pdf")}, headers=h)
    did = up.json()["data"]["id"]
    ex = c.post(f"/api/v1/documents/{did}/extract", headers=h)
    assert ex.status_code == 201, ex.text
    assert ex.json()["data"]["chunks"] >= 1
    hits = c.get("/api/v1/documents/search?q=Vantor", headers=h).json()["data"]
    assert len(hits) == 1 and hits[0]["documentId"] == did
    assert c.get("/api/v1/documents/search?q=Vantor", headers=_h(pem, "other")).json()["data"] == []
    # scanned image quarantines honestly
    up2 = c.post("/api/v1/documents", files={"file": ("scan.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64), "image/png")}, headers=h)
    ex2 = c.post(f"/api/v1/documents/{up2.json()['data']['id']}/extract", headers=h)
    assert ex2.json()["data"]["quarantined"] is True
