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


# --- VNT-011: archive bombs ---------------------------------------------------


def _zip_with(entries: dict[str, bytes], *, compresslevel: int = 9) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=compresslevel) as z:
        for name, payload in entries.items():
            z.writestr(name, payload)
    return buf.getvalue()


def test_archive_with_too_many_entries_is_refused(monkeypatch):
    """A million-entry container is refused from the central directory, unread."""
    from app.core.config import get_settings
    from app.services.extract import ExtractError

    monkeypatch.setenv("MAX_ARCHIVE_ENTRIES", "5")
    get_settings.cache_clear()
    bomb = _zip_with({f"word/part{i}.xml": b"<a/>" for i in range(50)})
    with pytest.raises(ExtractError) as caught:
        extract("bomb.docx", bomb)
    assert caught.value.code == "DOC_ARCHIVE_TOO_MANY_ENTRIES"
    assert caught.value.details["maxEntries"] == 5
    get_settings.cache_clear()


def test_oversized_entry_is_refused_before_it_is_decompressed(monkeypatch):
    from app.core.config import get_settings
    from app.services.extract import ExtractError

    monkeypatch.setenv("MAX_ENTRY_BYTES", "4096")
    get_settings.cache_clear()
    # 200 KB of zeroes compresses to a few hundred bytes: a textbook bomb.
    bomb = _zip_with({"word/document.xml": b"a" * 200_000})
    assert len(bomb) < 4096, "the compressed form must be small for this to be a bomb"
    with pytest.raises(ExtractError) as caught:
        extract("bomb.docx", bomb)
    assert caught.value.code in {"DOC_ARCHIVE_ENTRY_TOO_LARGE", "DOC_ARCHIVE_SUSPICIOUS_RATIO"}
    get_settings.cache_clear()


def test_implausible_compression_ratio_is_refused(monkeypatch):
    """Even with plausible-looking declared sizes, a 1000x ratio is a bomb."""
    from app.core.config import get_settings
    from app.services.extract import ExtractError

    monkeypatch.setenv("MAX_COMPRESSION_RATIO", "50")
    get_settings.cache_clear()
    bomb = _zip_with({"word/document.xml": b"\0" * 500_000})
    with pytest.raises(ExtractError) as caught:
        extract("bomb.docx", bomb)
    assert caught.value.code == "DOC_ARCHIVE_SUSPICIOUS_RATIO"
    get_settings.cache_clear()


def test_a_lying_uncompressed_size_cannot_exceed_the_declared_cap(monkeypatch):
    """The per-entry check and the read must trust the *same* field.

    Every limit in `_BudgetedArchive` is derived from `ZipInfo.file_size`, and
    `ZipFile.read()` is expected to stop at that same number. If either side
    instead drained the real stream, the check would be decorative — an attacker
    would declare a 1 KB member and expand 48 MiB.

    This is the assumption the whole design rests on, so it is asserted rather
    than trusted: a standard library change that made `read()` honour the real
    stream would turn every limit here into a comment.
    """
    import io
    import struct
    import zipfile

    from app.core.config import get_settings

    monkeypatch.setenv("MAX_ENTRY_BYTES", "4096")
    get_settings.cache_clear()

    # An honest archive of 48 MiB of zeroes: ~48 KiB on the wire.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("word/document.xml", b"\0" * (48 * 1024 * 1024))
    blob = buf.getvalue()
    # deflate tops out near 1032:1, so 48 MiB of zeroes is ~48 KiB on the wire:
    # small enough to be a bomb, which is the whole point.
    assert len(blob) < 64 * 1024, f"expected a small archive, got {len(blob)} bytes"
    assert len(blob) * 100 < 48 * 1024 * 1024, "the compression must be implausible"

    # Now rewrite the uncompressed-size field in both the local header and the
    # central directory, so the archive claims to be tiny.
    patched = bytearray(blob)
    local = patched.find(b"PK\x03\x04")
    central = patched.find(b"PK\x01\x02")
    struct.pack_into("<I", patched, local + 22, 1024)
    struct.pack_into("<I", patched, central + 24, 1024)
    lying = bytes(patched)

    with zipfile.ZipFile(io.BytesIO(lying)) as zf:
        assert zf.getinfo("word/document.xml").file_size == 1024
        try:
            data = zf.read("word/document.xml")
        except zipfile.BadZipFile:
            # CPython stops at the declared size and then fails the CRC check.
            # Failing closed is the acceptable outcome: nothing is returned.
            data = b""
        assert len(data) <= 1024, (
            f"read() returned {len(data)} bytes for a member declaring 1024; "
            "the per-entry cap can be lied past")

    get_settings.cache_clear()


def test_cumulative_budget_is_enforced_across_many_valid_members(monkeypatch):
    """The backstop for a directory that lies: every member individually passes,
    and the total does not.

    Uses a workbook, because the sheet loop is the one that iterates *every*
    matching entry — a DOCX reads a single named part, so it could not exercise
    a cumulative budget at all.
    """
    from app.core.config import get_settings
    from app.services.extract import ExtractError

    monkeypatch.setenv("MAX_ENTRY_BYTES", str(64 * 1024))
    monkeypatch.setenv("MAX_COMPRESSION_RATIO", "100000")
    monkeypatch.setenv("MAX_ARCHIVE_BYTES", str(200 * 1024))
    monkeypatch.setenv("MAX_ARCHIVE_ENTRIES", "1000")
    get_settings.cache_clear()
    # A repeating byte ramp: 51 KB per sheet, each under the per-entry cap.
    payload = bytes(range(256)) * 200
    bomb = _zip_with({f"xl/worksheets/sheet{i}.xml": payload for i in range(20)})
    with pytest.raises(ExtractError) as caught:
        extract("bomb.xlsx", bomb)
    assert caught.value.code == "DOC_ARCHIVE_TOO_LARGE"
    get_settings.cache_clear()


def test_pdf_flate_bomb_is_refused(monkeypatch):
    """The PDF path expanded a Flate stream with no output bound at all."""
    import zlib

    from app.core.config import get_settings
    from app.services.extract import ExtractError

    monkeypatch.setenv("MAX_ARCHIVE_BYTES", str(64 * 1024))
    get_settings.cache_clear()
    payload = zlib.compress(b"BT (aaaa bbbb cccc dddd) Tj ET " * 20_000, 9)
    pdf = (b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n"
           + payload + b"\nendstream\nendobj\ntrailer\n<<>>\n")
    assert len(pdf) < 200 * 1024, "the compressed PDF must be small"
    with pytest.raises(ExtractError) as caught:
        extract("bomb.pdf", pdf)
    assert caught.value.code == "DOC_ARCHIVE_TOO_LARGE"
    get_settings.cache_clear()


def test_limits_come_from_settings_not_hardcoded(monkeypatch):
    """A generous limit must let a large-but-legitimate document through."""
    from app.core.config import get_settings

    monkeypatch.setenv("MAX_ENTRY_BYTES", str(8 * 1024 * 1024))
    monkeypatch.setenv("MAX_ARCHIVE_BYTES", str(64 * 1024 * 1024))
    monkeypatch.setenv("MAX_COMPRESSION_RATIO", "10000")
    get_settings.cache_clear()
    big = b"word text " * 20_000  # ~200 KB of real content
    out = extract("big.docx", _zip_with({"word/document.xml":
                                         b'<w:document xmlns:w="x"><w:t>' + big + b"</w:t></w:document>"}))
    assert "word text" in out.text
    get_settings.cache_clear()


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


def _h(pem: bytes, tenant="t1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u1", "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "ex-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_extract_search_flow(client):
    c, pem = client
    h = _h(pem, "acme")
    up = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(_pdf_hello()), "application/pdf")}, headers=h)
    did = up.json()["data"]["id"]
    ex = c.post(f"/api/v1/documents/{did}/extract", headers=h)
    # 200, not 201: extraction is idempotent per document (re-extract replaces
    # chunks) and a quarantine is a real 200 outcome, not a created resource.
    assert ex.status_code == 200, ex.text
    assert ex.json()["data"]["chunks"] >= 1
    hits = c.get("/api/v1/documents/search?q=Vantor", headers=h).json()["data"]
    assert len(hits) == 1 and hits[0]["documentId"] == did
    assert c.get("/api/v1/documents/search?q=Vantor", headers=_h(pem, "other")).json()["data"] == []
    # scanned image quarantines honestly
    up2 = c.post("/api/v1/documents", files={"file": ("scan.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64), "image/png")}, headers=h)
    ex2 = c.post(f"/api/v1/documents/{up2.json()['data']['id']}/extract", headers=h)
    assert ex2.status_code == 200
    assert ex2.json()["data"]["quarantined"] is True


def test_extract_requires_write_role(client):
    """Extraction mutates status + rewrites chunks — Read-Only must be refused."""
    c, pem = client
    up = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(_pdf_hello()), "application/pdf")},
                headers=_h(pem, "acme"))
    did = up.json()["data"]["id"]
    ro = _h(pem, "acme", roles=("Read Only", "Auditor"))
    r = c.post(f"/api/v1/documents/{did}/extract", headers=ro)
    assert r.status_code == 403, r.text
    # ...and upload is refused for the same role, so the gate is not extract-only
    assert c.post("/api/v1/documents", files={"file": ("x.pdf", io.BytesIO(_pdf_hello()), "application/pdf")},
                  headers=ro).status_code == 403
    # a real write role still works
    assert c.post(f"/api/v1/documents/{did}/extract", headers=_h(pem, "acme", roles=("Category Manager",))).status_code == 200
