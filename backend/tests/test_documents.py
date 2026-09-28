"""Document Wave 1 tests — validation, dedupe, hash-verified download, tamper quarantine."""
import io
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

ISS = "https://issuer.test/realms/vantor"
AUD = "vantor-web"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OIDC_ISSUER", ISS)
    monkeypatch.setenv("JWT_AUDIENCE", AUD)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.setenv("S3_BUCKET", "")
    from app.core.config import get_settings
    from app.core.tenant import get_engine, reset_engine_cache
    from app.services.document import reset_storage_cache

    get_settings.cache_clear()
    reset_engine_cache()
    reset_storage_cache()
    engine = get_engine()
    from app.models.registry import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    jwk = RSAAlgorithm.to_jwk(priv.public_key(), as_dict=True)
    jwk["kid"] = "d-kid"
    from app.core import security

    security.override_jwks({"d-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    reset_storage_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "buyer1", "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "d-kid"})
    return {"Authorization": f"Bearer {tok}"}


PDF = b"%PDF-1.4 fake body for tests"


def test_upload_download_dedupe(client):
    c, pem = client
    h = _h(pem, "acme")
    r = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(PDF), "application/pdf")}, headers=h)
    assert r.status_code == 201, r.text
    did = r.json()["data"]["id"]
    assert r.json()["data"]["deduped"] is False
    assert r.json()["data"]["kind"] == "pdf"
    r2 = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(PDF), "application/pdf")}, headers=h)
    assert r2.json()["data"]["deduped"] is True
    assert r2.json()["data"]["id"] == did
    dl = c.get(f"/api/v1/documents/{did}/download", headers=h)
    assert dl.status_code == 200
    assert dl.content == PDF
    assert c.get("/api/v1/documents", headers=_h(pem, "other")).json()["data"] == []


def test_blocked_extension_and_empty_file(client):
    c, pem = client
    h = _h(pem, "t9")
    r = c.post("/api/v1/documents", files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}, headers=h)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "DOC_TYPE_BLOCKED"
    from app.services.document import DocumentError, check_size, validate_filename

    for bad in ("evil.exe", ".hidden", "", "a" * 300 + ".pdf"):
        with pytest.raises(DocumentError):
            validate_filename(bad)
    with pytest.raises(DocumentError):
        check_size(0)


def test_content_must_match_the_extension(client):
    """VNT-012: a PNG named `.pdf` used to be accepted, because the sniffed kind
    was never compared with the claimed one and `.tiff` needed no bytes at all.
    """
    c, pem = client
    h = _h(pem, "t9")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    mismatch = c.post("/api/v1/documents", files={"file": ("invoice.pdf", io.BytesIO(png), "application/pdf")}, headers=h)
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "DOC_TYPE_MISMATCH"
    assert mismatch.json()["error"]["details"]["detected"] == "png"

    # A real PNG with the right name is accepted.
    ok = c.post("/api/v1/documents", files={"file": ("logo.png", io.BytesIO(png), "image/png")}, headers=h)
    assert ok.status_code == 201, ok.text

    # Arbitrary bytes claiming an allowlisted extension are refused outright.
    junk = c.post("/api/v1/documents", files={"file": ("notes.pdf", io.BytesIO(b"just some text"), "application/pdf")}, headers=h)
    assert junk.status_code == 422
    assert junk.json()["error"]["code"] == "DOC_TYPE_UNVERIFIED"


def test_declared_mime_must_agree_with_the_bytes(client):
    c, pem = client
    h = _h(pem, "t9")
    wrong = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(PDF), "image/png")}, headers=h)
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "DOC_MIME_MISMATCH"


def test_docx_and_xlsx_are_distinguished_by_archive_contents(client):
    """Both are `PK\\x03\\x04`; only the contents tell them apart."""
    import zipfile

    def office_zip(part: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(part, "<root><t>hello</t></root>")
        return buf.getvalue()

    docx = office_zip("word/document.xml")
    xlsx = office_zip("xl/workbook.xml")

    c, pem = client
    h = _h(pem, "t9")
    # Claimed as .xlsx but it is a docx: refused.
    swapped = c.post("/api/v1/documents", files={"file": ("sheet.xlsx", io.BytesIO(docx), "application/octet-stream")}, headers=h)
    assert swapped.status_code == 422
    assert swapped.json()["error"]["details"]["detected"] == "ooxml-docx"

    for name, payload, kind in (("report.docx", docx, "ooxml-docx"), ("book.xlsx", xlsx, "ooxml-xlsx")):
        res = c.post("/api/v1/documents", files={"file": (name, io.BytesIO(payload), "application/octet-stream")}, headers=h)
        assert res.status_code == 201, (name, res.text)
        assert res.json()["data"]["kind"] == kind


def test_upload_size_is_enforced_before_and_during_the_read(client, monkeypatch):
    """VNT-010: the whole body was read before the limit was consulted."""
    c, pem = client
    h = _h(pem, "t9")
    from app.core.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    oversized = PDF + b"\x00" * (1024 * 1024 + 16)
    r = c.post("/api/v1/documents", files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")}, headers=h)
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "DOC_TOO_LARGE"
    get_settings.cache_clear()


def test_ingest_aborts_mid_stream_rather_than_buffering_everything(monkeypatch):
    """The cap is enforced on the running total, not on the finished length."""
    from app.services.document import CHUNK_BYTES, DocumentError, ingest

    class SlowStream:
        """Yields more than the cap without ever materialising it in one read."""

        def __init__(self, total: int):
            self.sent = 0
            self.total = total
            self.headers = {}

        def read(self, n: int = -1) -> bytes:
            if self.sent >= self.total:
                return b""
            block = min(n, self.total - self.sent)
            self.sent += block
            return b"%PDF-" + b"\x00" * max(0, block - 5)

    stream = SlowStream(64 * 1024 * 1024)
    with pytest.raises(DocumentError) as caught:
        ingest(stream, filename="x.pdf", max_bytes=2 * 1024 * 1024)
    assert caught.value.code == "DOC_TOO_LARGE"
    # The point: it stopped early rather than reading all 64 MB.
    assert stream.sent < 64 * 1024 * 1024
    assert stream.sent <= 2 * CHUNK_BYTES + CHUNK_BYTES


def test_ingest_refuses_on_declared_length_before_reading(monkeypatch):
    from app.services.document import DocumentError, ingest

    class LyingStream:
        sent = 0

        def __init__(self):
            self.headers = {"content-length": str(10 * 1024 * 1024 * 1024)}

        def read(self, n: int = -1) -> bytes:
            LyingStream.sent += 1
            return b""

    with pytest.raises(DocumentError) as caught:
        ingest(LyingStream(), filename="x.pdf", max_bytes=1024 * 1024)
    assert caught.value.code == "DOC_TOO_LARGE"
    assert LyingStream.sent == 0, "a declared oversize must be refused without reading a byte"


def test_resource_reference_is_target_validated(client):
    """VNT-013: `resource_id` was length-checked only, so a cross-tenant id was
    accepted with 201. A resource name maps to exactly one model, so it is checkable.
    """
    c, pem = client
    h = _h(pem, "t9")
    sup = c.post("/api/v1/suppliers", json={"code": "SUP-D9", "name": "Doc Co"}, headers=h).json()["data"]["id"]

    ok = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(PDF), "application/pdf")},
                data={"resource": "supplier", "resource_id": sup}, headers=h)
    assert ok.status_code == 201, ok.text

    # An id from another tenant is refused.
    other = c.post("/api/v1/suppliers", json={"code": "SUP-OTH", "name": "Other Co"},
                   headers=_h(pem, "other")).json()["data"]["id"]
    cross = c.post("/api/v1/documents", files={"file": ("x2.pdf", io.BytesIO(PDF + b"2"), "application/pdf")},
                   data={"resource": "supplier", "resource_id": other}, headers=h)
    assert cross.status_code == 422
    assert cross.json()["error"]["code"] == "UNKNOWN_SUPPLIER"

    # A resource name that is not attachable is refused, with the list attached.
    bogus = c.post("/api/v1/documents", files={"file": ("x3.pdf", io.BytesIO(PDF + b"3"), "application/pdf")},
                   data={"resource": "quote", "resource_id": sup}, headers=h)
    assert bogus.status_code == 422
    assert bogus.json()["error"]["code"] == "REFERENCE_UNKNOWN_RESOURCE"

    # Half a reference is a mistake worth naming.
    half = c.post("/api/v1/documents", files={"file": ("x4.pdf", io.BytesIO(PDF + b"4"), "application/pdf")},
                  data={"resource": "supplier"}, headers=h)
    assert half.status_code == 422
    assert half.json()["error"]["code"] == "REFERENCE_INCOMPLETE"


def test_tampered_bytes_are_quarantined_not_served(client, tmp_path):
    """The integrity re-check is what turns silent corruption into a refusal."""
    import os

    c, pem = client
    h = _h(pem, "t9")
    r = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(PDF), "application/pdf")}, headers=h)
    did = r.json()["data"]["id"]
    # Corrupt the bytes on disk behind the API's back.
    from app.core.config import get_settings

    root = get_settings().upload_dir
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            target = os.path.join(dirpath, name)
            with open(target, "r+b") as f:
                f.seek(0)
                f.write(b"XXXX")
    dl = c.get(f"/api/v1/documents/{did}/download", headers=h)
    assert dl.status_code == 409
    row = c.get("/api/v1/documents", headers=h).json()["data"][0]
    assert row["status"] == "quarantined"
