"""Integration tests — adapter contract, webhook validation, HMAC fanout, tenant scope."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

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
    jwk["kid"] = "in-kid"
    from app.core import security

    security.override_jwks({"in-kid": RSAAlgorithm.from_jwk(jwk)})
    from app.main import app as fastapi_app

    c = TestClient(fastapi_app, raise_server_exceptions=False)
    yield c, pem
    security.override_jwks(None)
    Base.metadata.drop_all(engine)
    reset_engine_cache()
    get_settings.cache_clear()


def _h(pem: bytes, tenant="t1", sub="u1", roles=("Buyer",)):
    now = datetime.now(timezone.utc)
    tok = jwt.encode({"iss": ISS, "aud": AUD, "sub": sub, "tenant_id": tenant,
                      "realm_access": {"roles": list(roles)},
                      "exp": now + timedelta(minutes=5), "iat": now},
                     pem, algorithm="RS256", headers={"kid": "in-kid"})
    return {"Authorization": f"Bearer {tok}"}


#: A genuinely public address for the stubbed resolver. RFC 5737 documentation
#: ranges will not do: `ipaddress` correctly reports 203.0.113.0/24 (and the
#: other TEST-NETs) as private, because nobody should be dialling documentation
#: space — which the address policy then refuses, as it should.
PUBLIC_TEST_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _stub_dns(monkeypatch):
    monkeypatch.setattr("app.services.egress._resolve",
                        lambda host, port: (PUBLIC_TEST_IP,))
    monkeypatch.delenv("WEBHOOK_EGRESS_ALLOWLIST", raising=False)


def test_types_and_registration_guards(client):
    c, pem = client
    h = _h(pem, "acme")
    assert "logging" in c.get("/api/v1/integrations/types", headers=h).json()["data"]["adapters"]
    assert c.post("/api/v1/integrations", json={"name": "X", "itype": "teleport"}, headers=h).status_code == 422
    # raw secrets refused — vault refs only
    bad = c.post("/api/v1/integrations", json={"name": "Mail", "itype": "email", "secret_ref": "notavaultref-must-be-refused-1"}, headers=h)
    assert bad.status_code == 422
    ok = c.post("/api/v1/integrations", json={"name": "Mail", "itype": "email", "secret_ref": "env:MAIL_KEY"}, headers=h)
    assert ok.status_code == 201
    # non-https webhooks refused
    assert c.post("/api/v1/webhooks/endpoints", json={"url": "http://x.test/h"}, headers=h).status_code == 422
    ep = c.post("/api/v1/webhooks/endpoints", json={"url": "https://x.test/h", "events": ["ping"]}, headers=h)
    assert ep.status_code == 201, ep.text
    eid = ep.json()["data"]["id"]
    # A ping whose endpoint has no resolvable secret is dead-lettered, never
    # raised. `dead` rather than `pending`: an absent signing secret is a
    # configuration error that retrying cannot fix.
    t = c.post("/api/v1/webhooks/test", json={"endpoint_id": eid}, headers=h)
    assert t.status_code == 200, t.text
    assert t.json()["data"]["delivery"]["status"] == "dead"
    assert c.get("/api/v1/webhooks/deliveries?status=dead", headers=h).json()["data"] != []
    assert c.get("/api/v1/webhooks/deliveries", headers=_h(pem, "other")).json()["data"] == []


def test_egress_refuses_internal_destinations_at_registration(client):
    """VNT-007: SSRF targets are refused where the tenant supplies them.

    Previously only `startswith("https://")` was checked, so a `Buyer` could
    register `https://169.254.169.254/latest/meta-data/` and have the server
    fetch cloud credentials on the next fanout. Each of these must be refused at
    *registration*, not discovered as a failed delivery later.
    """
    c, pem = client
    h = _h(pem, "ssrf")
    refused = [
        ("https://169.254.169.254/latest/meta-data/", "EGRESS_ADDRESS_REFUSED"),
        ("https://127.0.0.1:6379/", "EGRESS_ADDRESS_REFUSED"),
        ("https://[::1]/hook", "EGRESS_ADDRESS_REFUSED"),
        ("https://10.0.0.5/hook", "EGRESS_ADDRESS_REFUSED"),
        ("https://192.168.1.1/hook", "EGRESS_ADDRESS_REFUSED"),
        ("https://172.16.0.1/hook", "EGRESS_ADDRESS_REFUSED"),
        ("https://[fd00::1]/hook", "EGRESS_ADDRESS_REFUSED"),
        ("https://localhost/hook", "EGRESS_HOST_REFUSED"),
        ("https://metadata.google.internal/x", "EGRESS_HOST_REFUSED"),
        ("https://app.internal/hook", "EGRESS_HOST_REFUSED"),
        ("https://internal-postgres/hook", "EGRESS_BARE_HOSTNAME_REFUSED"),
        ("https://user@x.test/h", "EGRESS_USERINFO_REFUSED"),
        ("https://trusted.example@evil.test/h", "EGRESS_USERINFO_REFUSED"),
        ("file:///etc/passwd", "EGRESS_SCHEME_REFUSED"),
        ("gopher://x.test/", "EGRESS_SCHEME_REFUSED"),
        ("http://x.test/h", "EGRESS_SCHEME_REFUSED"),
    ]
    for url, code in refused:
        res = c.post("/api/v1/webhooks/endpoints", json={"url": url}, headers=h)
        assert res.status_code == 422, f"{url} was accepted: {res.text}"
        assert res.json()["error"]["code"] == code, f"{url}: expected {code}, got {res.text}"


def test_egress_refuses_a_name_that_resolves_to_an_internal_address(client, monkeypatch):
    """A public-looking name that resolves inward is the DNS-rebinding primitive.

    The host passes every syntactic check and the address policy is what catches
    it, which is why the policy runs against the *resolved* address.
    """
    monkeypatch.setattr("app.services.egress._resolve", lambda host, port: ("10.1.2.3",))
    c, pem = client
    h = _h(pem, "rebind")
    res = c.post("/api/v1/webhooks/endpoints", json={"url": "https://sneaky.example/hook"}, headers=h)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "EGRESS_ADDRESS_REFUSED"
    assert "10.1.2.3" in res.text


def test_egress_allowlist_is_enforced_when_configured(client, monkeypatch):
    """When WEBHOOK_EGRESS_ALLOWLIST is set, only those hosts are dialled."""
    monkeypatch.setenv("WEBHOOK_EGRESS_ALLOWLIST", "hooks.acme.test")
    c, pem = client
    h = _h(pem, "allow")
    assert c.post("/api/v1/webhooks/endpoints",
                  json={"url": "https://hooks.acme.test/hook"}, headers=h).status_code == 201
    # A subdomain of an allowed entry is allowed; a different domain is not.
    assert c.post("/api/v1/webhooks/endpoints",
                  json={"url": "https://eu.hooks.acme.test/hook"}, headers=h).status_code == 201
    denied = c.post("/api/v1/webhooks/endpoints", json={"url": "https://x.test/hook"}, headers=h)
    assert denied.status_code == 422
    assert denied.json()["error"]["code"] == "EGRESS_HOST_NOT_ALLOWLISTED"
    # Suffix confusion: "notacme.test" must not match "acme.test".
    lookalike = c.post("/api/v1/webhooks/endpoints", json={"url": "https://evilacme.test/hook"}, headers=h)
    assert lookalike.status_code == 422


def test_hmac_sign_verify():
    from app.services.integration import Adapter, canonical, resolve_secret, sign

    body = canonical({"event": "ping", "n": 1})
    assert sign("s3cret", body) == sign("s3cret", body)
    assert sign("a", body) != sign("b", body)
    assert resolve_secret("env:DEFINITELY_NOT_SET_XYZ") == ""
    assert resolve_secret("notavaultref-must-be-refused-2") == ""
    with pytest.raises(NotImplementedError):
        Adapter().send("x", {})


def _seed_endpoints(tenant_id: str, urls: list[str]) -> None:
    from app.core.tenant import pinned_session
    from app.models.integration import WebhookEndpoint

    db = pinned_session(tenant_id)
    try:
        for url in urls:
            db.add(WebhookEndpoint(tenant_id=tenant_id, created_by="", updated_by="",
                                   url=url, events=["ping"], status="active",
                                   secret_ref="env:HOOK_KEY"))
        db.commit()
    finally:
        db.close()


def _fanout(tenant_id: str):
    """`fanout` only flushes — the caller owns the commit, exactly as the router does."""
    from app.core.tenant import pinned_session
    from app.services.integration import fanout

    db = pinned_session(tenant_id)
    try:
        out = fanout(db, tenant_id=tenant_id, event="ping", payload={"x": 1})
        db.commit()
        return out
    finally:
        db.close()


def _drain(tenant_id: str, **kw):
    from app.core.tenant import pinned_session
    from app.services.integration import drain

    db = pinned_session(tenant_id)
    try:
        return drain(db, tenant_id=tenant_id, **kw)
    finally:
        db.close()


def _deliveries(tenant_id: str) -> list:
    from app.core.tenant import pinned_session
    from app.models.integration import WebhookDelivery

    db = pinned_session(tenant_id)
    try:
        return list(db.execute(select(WebhookDelivery).where(
            WebhookDelivery.tenant_id == tenant_id).order_by(WebhookDelivery.created_at)).scalars())
    finally:
        db.close()


class _Calls(list):
    """Registered destination URLs, with the pinned requests alongside.

    Assertions in this file read the list as URLs. `calls.requests` holds the
    `httpx.Request` objects actually sent, which is where the address pinning is
    observable — the URL on those requests carries an IP, not a hostname.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list = []


def _fake_transport(monkeypatch, *, status_code: int = 200, raise_exc: Exception | None = None,
                    record: list | None = None):
    """Patch the HTTP call inside the egress layer, bypassing real DNS and sockets."""
    import httpx

    from app.services import integration

    calls = record if record is not None else _Calls()

    def _original_url(request) -> str:
        """Rebuild the registered URL from a pinned request.

        The request's own URL has the validated IP in it, so the destination the
        test cares about lives in the `Host` header. Reading it back from there is
        also a useful assertion in itself: if the pinning ever stopped setting
        `Host`, this would not be the URL anyone registered.
        """
        url = request.url
        query = f"?{url.query.decode()}" if url.query else ""
        return f"https://{request.headers['Host']}{url.path}{query}"

    class _Response:
        """Minimal `httpx.Response` surface: status_code + raise_for_status."""

        def __init__(self, code: int):
            self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"HTTP {self.status_code}", request=None, response=None)

    class C:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send(self, request, **kw):
            # The delivery path uses `send`, not `post`, because the request has
            # to be built by hand: it carries the pinned address in the URL, the
            # original name in `Host`, and the SNI override that keeps
            # certificate verification pointed at the real hostname. Stubbing
            # `post` here would have let the pinning regress unnoticed.
            calls.requests.append(request)
            calls.append(_original_url(request))
            if raise_exc is not None:
                raise raise_exc
            return _Response(status_code)

        def post(self, url, **kw):  # pragma: no cover - must not be used
            raise AssertionError(
                "delivery must use the pinned request via send(), not post() on the "
                "hostname: post() re-resolves the name and reopens the DNS-rebinding "
                "window that assert_safe_to_dial exists to close")

    monkeypatch.setattr(integration.httpx, "Client", C)
    return calls

    monkeypatch.setattr(integration.httpx, "Client", C)
    return calls


def test_delivery_is_pinned_to_the_validated_address(client, monkeypatch, _stub_dns):
    """The socket must open to the address that was checked.

    `assert_safe_to_dial` re-resolves the host and hands back an address. If the
    request that is then sent is built from the *hostname*, the client resolves
    it a second time and the rebinding window is open again — the validation
    still ran, the audit trail still says it ran, and the protection is not
    there. An earlier version of `_deliver_once` did exactly that: it discarded
    the returned address and posted to the URL.
    """
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    sent = _fake_transport(monkeypatch, status_code=200)
    _seed_endpoints("t1", ["https://consumer.test/hook"])
    _fanout("t1")
    _drain("t1")

    assert len(sent.requests) == 1, "nothing was delivered"
    request = sent.requests[0]
    # The URL authority is the literal address that was validated, not the name.
    assert request.url.host == "93.184.216.34", request.url.host
    # ... while the request still presents itself as the original name, because
    # the receiving virtual host routes on Host and the signature covers it.
    assert request.headers["Host"] == "consumer.test"
    # ... and TLS is verified against the original name rather than the literal.
    # Verifying against the IP would fail for every real certificate; disabling
    # verification instead would hand an attacker a valid cert for any host.
    assert request.extensions.get("sni_hostname") == "consumer.test"


def test_rebind_between_validation_and_dial_is_refused(client, monkeypatch):
    """A name that passes registration and re-resolves to an internal address
    at delivery time must be refused, not delivered.

    This is the attack the pinning exists for: an attacker-controlled resolver
    answers with a public address for the first lookup (registration passes) and
    with 127.0.0.1 for the second (the connection would go to the local Redis).
    """
    from app.services import egress

    monkeypatch.setenv("HOOK_KEY", "s3cret")
    monkeypatch.delenv("WEBHOOK_EGRESS_ALLOWLIST", raising=False)
    calls = {"n": 0}

    def rebinding(host, port):
        calls["n"] += 1
        return ("93.184.216.34",) if calls["n"] == 1 else ("127.0.0.1",)

    monkeypatch.setattr(egress, "_resolve", rebinding)
    sent = _fake_transport(monkeypatch, status_code=200)
    _seed_endpoints("t1", ["https://consumer.test/hook"])
    _fanout("t1")
    _drain("t1")

    assert not sent, f"a delivery reached the internal address: {sent}"
    delivery = _deliveries("t1")[0]
    assert delivery.status == "dead"
    assert "EGRESS_ADDRESS_REFUSED" in delivery.last_error


def test_a_public_ip_literal_url_is_accepted(client, monkeypatch):
    """A webhook URL may legitimately be an IP literal, and that path was broken.

    `validate_url` has a separate branch for IP literals that returns early - and
    it read `port` before the line that assigned it, so registering a hook against
    a public address raised `NameError` instead of being accepted. A linter
    (ruff F821) found it; no test had covered the branch, because every test used
    a hostname.
    """
    from app.services.egress import validate_url

    monkeypatch.delenv("WEBHOOK_EGRESS_ALLOWLIST", raising=False)
    target = validate_url("https://93.184.216.34/hooks/v1?tenant=acme")
    assert target.host == "93.184.216.34"
    assert target.port == 443
    assert target.addresses == ("93.184.216.34",)
    # The path and query survive, so a signed payload lands on the right resource.
    assert target.path == "/hooks/v1"
    assert target.query == "tenant=acme"

    # An explicit port is honoured rather than defaulted.
    assert validate_url("https://93.184.216.34:8443/hook").port == 8443


def test_an_internal_ip_literal_is_still_refused(client, monkeypatch):
    """The fix must not have loosened the address policy."""
    from app.services.egress import EgressError, validate_url

    monkeypatch.delenv("WEBHOOK_EGRESS_ALLOWLIST", raising=False)
    for url in ("https://127.0.0.1/hook", "https://10.0.0.5/hook",
                "https://169.254.169.254/latest/meta-data/"):
        with pytest.raises(EgressError) as caught:
            validate_url(url)
        assert caught.value.code == "EGRESS_ADDRESS_REFUSED", url


def test_duplicate_endpoint_urls_are_enqueued_once(client, monkeypatch):
    """Two registrations of the same URL must not double-fire the consumer.

    `webhook_endpoints.url` carries no unique constraint, so a tenant could
    register the same endpoint twice. The extra registration is reported as
    `skipped_duplicate` and only one delivery is queued, so a consumer that is
    not idempotent sees one signed payload, not two.
    """
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _seed_endpoints("t1", ["https://consumer.test/hook", "https://consumer.test/hook",
                           "https://other.test/hook"])
    out = _fanout("t1")
    statuses = [o["status"] for o in out]
    assert statuses.count("skipped_duplicate") == 1
    assert statuses.count("pending") == 2

    sent = _fake_transport(monkeypatch)
    _drain("t1")
    assert sent.count("https://consumer.test/hook") == 1, sent
    assert sent.count("https://other.test/hook") == 1
    assert [d.status for d in _deliveries("t1")] == ["delivered", "delivered"]


def test_fanout_does_no_network_io_and_drain_delivers(client, monkeypatch):
    """VNT-008: the request path must not make network calls.

    Delivery used to be a synchronous `httpx.post` per endpoint inside the
    caller's request, with a 20s budget and no retry. `fanout` now only enqueues;
    the worker's `drain` is what talks to the network. This is the test that
    would have caught the original design, and it is the one that keeps it fixed.
    """
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    sent = _fake_transport(monkeypatch)
    _seed_endpoints("t1", ["https://a.test/hook", "https://b.test/hook"])

    _fanout("t1")
    assert sent == [], f"fanout performed network IO: {sent}"
    assert all(d.status == "pending" and d.attempts == 0 for d in _deliveries("t1"))

    results = _drain("t1")
    assert sorted(r["status"] for r in results) == ["delivered", "delivered"]
    assert sorted(sent) == ["https://a.test/hook", "https://b.test/hook"]


def test_failed_delivery_retries_with_backoff_then_dead_letters(client, monkeypatch):
    """VNT-008: `MAX_ATTEMPTS = 5` was defined and referenced nowhere.

    Now every attempt is counted, backoff is recorded on the row so a restart
    does not lose it, and the row is dead-lettered — not silently left `failed` —
    once the budget is spent.
    """
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _fake_transport(monkeypatch, raise_exc=OSError("connection reset"))
    _seed_endpoints("t1", ["https://flaky.test/hook"])
    _fanout("t1")

    for attempt in range(1, 6):
        # Make the row due again so each iteration is an attempt, not a skip.
        from app.core.tenant import pinned_session
        from app.models.integration import WebhookDelivery

        db = pinned_session("t1")
        try:
            row = db.execute(select(WebhookDelivery)).scalar_one()
            row.next_attempt_at = None
            db.commit()
        finally:
            db.close()
        _drain("t1")
        row = _deliveries("t1")[0]
        assert row.attempts == attempt, (attempt, row.attempts)
        if attempt < 5:
            assert row.status == "pending"
            assert row.next_attempt_at is not None, "a retryable row must schedule its next attempt"
        else:
            assert row.status == "dead", row.status
            assert row.next_attempt_at is None


def test_backoff_is_bounded_and_jittered(monkeypatch):
    """Jitter matters: without it a receiver that returns all at once is hit by
    every queued delivery in the same millisecond."""
    from app.services.integration import BACKOFF_CAP_S, backoff_seconds

    for attempts in range(1, 12):
        values = [backoff_seconds(attempts) for _ in range(50)]
        assert all(0 < v <= BACKOFF_CAP_S for v in values), (attempts, values[:3])
        assert len(set(values)) > 1, f"attempt {attempts} has no jitter"
    # Monotone in expectation: later attempts wait longer.
    assert sum(backoff_seconds(1) for _ in range(100)) < sum(backoff_seconds(6) for _ in range(100))


def test_backoff_not_yet_due_is_skipped(client, monkeypatch):
    """A row whose backoff has not elapsed must not be attempted."""
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("HOOK_KEY", "s3cret")
    sent = _fake_transport(monkeypatch)
    _seed_endpoints("t1", ["https://later.test/hook"])
    _fanout("t1")

    from app.core.tenant import pinned_session
    from app.models.integration import WebhookDelivery

    db = pinned_session("t1")
    try:
        row = db.execute(select(WebhookDelivery)).scalar_one()
        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    assert _drain("t1") == []
    assert sent == []


def test_redirect_is_refused(client, monkeypatch):
    """A 302 to an internal address is the easiest SSRF there is."""
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _fake_transport(monkeypatch, status_code=302)
    _seed_endpoints("t1", ["https://redirector.test/hook"])
    _fanout("t1")
    _drain("t1")
    row = _deliveries("t1")[0]
    # A redirect is permanent, so it dead-letters on the first attempt rather
    # than burning the retry budget on it.
    assert row.status == "dead", row.status
    assert "redirect" in row.last_error.lower()


def test_dead_letter_is_replayable(client, monkeypatch):
    """VNT-008: a dead letter must be recoverable without re-registering the endpoint."""
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _fake_transport(monkeypatch, raise_exc=OSError("boom"))
    _seed_endpoints("t1", ["https://recover.test/hook"])
    _fanout("t1")
    c, pem = client
    delivery_id = _deliveries("t1")[0].id

    # Replay is operator-only: a plain Buyer may not re-send a signed payload.
    buyer = _h(pem, "t1", sub="buyer1", roles=("Buyer",))
    assert c.post(f"/api/v1/webhooks/deliveries/{delivery_id}/replay", headers=buyer).status_code == 403

    ops = _h(pem, "t1", sub="ops1", roles=("Procurement Manager",))
    body = c.post(f"/api/v1/webhooks/deliveries/{delivery_id}/replay", headers=ops)
    assert body.status_code == 200, body.text
    assert body.json()["data"]["status"] == "pending"
    # The attempt counter resets, or a replay is instantly dead on first failure.
    assert _deliveries("t1")[0].attempts == 0


def test_replay_refuses_to_duplicate_a_successful_delivery(client, monkeypatch):
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _fake_transport(monkeypatch)
    _seed_endpoints("t1", ["https://ok.test/hook"])
    _fanout("t1")
    _drain("t1")
    delivered_id = _deliveries("t1")[0].id

    c, pem = client
    ops = _h(pem, "t1", sub="ops1", roles=("Procurement Manager",))
    res = c.post(f"/api/v1/webhooks/deliveries/{delivered_id}/replay", headers=ops)
    assert res.status_code == 409
    assert "duplicate" in res.text.lower()


def test_drain_endpoint_is_operator_only(client, monkeypatch):
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    _fake_transport(monkeypatch)
    _seed_endpoints("t1", ["https://x.test/hook"])
    _fanout("t1")
    c, pem = client
    assert c.post("/api/v1/webhooks/drain", headers=_h(pem, "t1", roles=("Buyer",))).status_code == 403
    ok = c.post("/api/v1/webhooks/drain",
                headers=_h(pem, "t1", sub="ops1", roles=("Procurement Manager",)))
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["results"][0]["status"] == "delivered"


def test_drain_never_touches_another_tenants_deliveries(client, monkeypatch):
    """The tenant filter in `drain` is the only thing stopping one tenant's worker
    from posting another tenant's webhook payload — and it used to be optional,
    defaulting to "no filter" when an argument was omitted. The property was never
    tested, which is why it could be weakened without anything going red.

    Both tenants have a pending delivery to a URL that records the call, so
    asserting on `sent` proves the second tenant's payload never left the system
    and not merely that its row kept its status.
    """
    monkeypatch.setenv("HOOK_KEY", "s3cret")
    sent = _fake_transport(monkeypatch)
    _seed_endpoints("t1", ["https://one.test/hook"])
    _seed_endpoints("t2", ["https://two.test/hook"])
    _fanout("t1")
    _fanout("t2")
    assert [d.status for d in _deliveries("t1")] == ["pending"]
    assert [d.status for d in _deliveries("t2")] == ["pending"]

    assert _drain("t1")

    assert [d.status for d in _deliveries("t1")] == ["delivered"]
    assert [d.status for d in _deliveries("t2")] == ["pending"], "drain crossed a tenant boundary"
    assert list(sent) == ["https://one.test/hook"], sent


def test_drain_requires_a_tenant_rather_than_defaulting_to_all_of_them():
    """A required argument is the fix; this is the assertion that keeps it that
    way, because the old signature (`tenant_id=""`) was not wrong-looking enough
    to survive review on its own merits."""
    import inspect

    from app.services.integration import drain

    param = inspect.signature(drain).parameters["tenant_id"]
    assert param.default is inspect.Parameter.empty, (
        "drain must not have a default tenant: an empty string read as 'every tenant'"
    )


def test_delivery_log_exposes_every_reachable_state(client, monkeypatch):
    """VNT-008: the log's own `?status=` filter used to reject a status the code
    wrote, so deferred rows were unreachable through the API reporting them."""
    c, pem = client
    h = _h(pem, "acme")
    from app.models.integration import DELIVERY_STATUSES

    for status in sorted(DELIVERY_STATUSES):
        assert c.get(f"/api/v1/webhooks/deliveries?status={status}", headers=h).status_code == 200, status
    bad = c.get("/api/v1/webhooks/deliveries?status=queued", headers=h)
    assert bad.status_code == 422, "`queued` was removed from the state machine and must not be accepted"


def test_registered_integrations_and_endpoints_are_listable(client):
    """Both list routes were missing entirely.

    The Integrations screen called `GET /api/v1/integrations` on every load and
    got a 405, which failed the whole page; and `POST /webhooks/test` needs an
    `endpoint_id` that no route could supply. Covered here so neither can be
    dropped again.
    """
    c, pem = client
    h = _h(pem)

    assert c.get("/api/v1/integrations", headers=h).json()["data"] == []
    assert c.get("/api/v1/webhooks/endpoints", headers=h).json()["data"] == []

    made = c.post("/api/v1/integrations", json={"name": "SAP S/4HANA", "itype": "erp",
                  "secret_ref": "env:ERP_TOKEN"}, headers=h)
    assert made.status_code == 201
    listed = c.get("/api/v1/integrations", headers=h).json()["data"]
    assert [r["name"] for r in listed] == ["SAP S/4HANA"]
    assert listed[0]["itype"] == "erp"
    # Registration is deliberately inert until an operator enables it.
    assert listed[0]["status"] == "disabled"
    # A vault pointer, never a secret — POST refuses anything else.
    assert listed[0]["secretRef"] == "env:ERP_TOKEN"

    ep = c.post("/api/v1/webhooks/endpoints", json={"url": "https://hooks.example.com/vantor",
                "events": ["RFQ_AWARDED"]}, headers=h)
    assert ep.status_code == 201
    eps = c.get("/api/v1/webhooks/endpoints", headers=h).json()["data"]
    assert len(eps) == 1
    assert eps[0]["events"] == ["RFQ_AWARDED"]
    # The id the test-ping route requires is now reachable from the API.
    assert eps[0]["id"] == ep.json()["data"]["id"]


def test_integration_list_is_tenant_scoped(client):
    c, pem = client
    c.post("/api/v1/integrations", json={"name": "Acme ERP", "itype": "erp"}, headers=_h(pem, tenant="acme"))
    other = c.get("/api/v1/integrations", headers=_h(pem, tenant="globex")).json()["data"]
    assert other == []
