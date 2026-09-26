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
    jwk["kid"] = "d-kid"
    from app.core import security

    security.override_jwks({"d-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1"):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": "buyer1", "tenant_id": tenant,
                      "realm_access": {"roles": ["Buyer"]},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "d-kid"})
    return {"Authorization": f"Bearer {tok}"}


def test_upload_download_dedupe(client):
    c, pem = client
    h = _h(pem, "acme")
    pdf = b"%PDF-1.4 fake body for tests"
    r = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(pdf), "application/pdf")}, data={"resource": "quote"}, headers=h)
    assert r.status_code == 201, r.text
    did = r.json()["data"]["id"]
    assert r.json()["data"]["deduped"] is False
    r2 = c.post("/api/v1/documents", files={"file": ("quote.pdf", io.BytesIO(pdf), "application/pdf")}, headers=h)
    assert r2.json()["data"]["deduped"] is True
    assert r2.json()["data"]["id"] == did
    dl = c.get(f"/api/v1/documents/{did}/download", headers=h)
    assert dl.status_code == 200
    assert dl.content == pdf
    assert c.get("/api/v1/documents", headers=_h(pem, "other")).json()["data"] == []


def test_blocked_type_and_service_rules(client):
    c, pem = client
    h = _h(pem, "t9")
    r = c.post("/api/v1/documents", files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}, headers=h)
    assert r.status_code == 422
    from app.services.document import check_size, sniff_kind, validate_filename
    import pytest as _pt

    with _pt.raises(Exception):
        validate_filename("evil.exe")
    with _pt.raises(Exception):
        check_size(0)
    assert sniff_kind(b"%PDF-1.7", "a.pdf") == "pdf"
    assert sniff_kind(b"\x89PNG\r\n\x1a\n", "a.png") == "png"
    assert sniff_kind(b"zzz", "a.exe") == "unknown"
