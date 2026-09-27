"""Shared test helpers.

`category_id` columns are validated against real `categories` rows (there is no
FOREIGN KEY in this schema, so the API refuses a dangling id itself). Tests that
need a categorised PO must therefore create the category first and pass the id
it got back — passing a literal like "CAT-A" used to work only because the write
path accepted an id that pointed at nothing.

`qualified_supplier` and `rfq_line_ids` exist because of the bid-evaluation gate
(VNT-020) and the quote-currency/line-mapping rules (VNT-021). Both used to be
optional in a way that made the controls unverifiable: a quote with no
`rfq_line_id` was accepted, and a `draft` supplier with no qualification could
win a contract. A test that exercises sourcing now has to set up a supplier that
could legally bid, which is what a real buyer does.
"""
from __future__ import annotations


def make_category(client, headers, code: str, name: str = "", parent_id: str = "") -> str:
    """Create a category and return its id, asserting the write succeeded."""
    r = client.post("/api/v1/catalog/categories",
                    json={"code": code, "name": name or code.title(), "parent_id": parent_id},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


#: The reviewer's roles. VNT-025/026 made certification verification and the
#: qualification decision capabilities distinct from supplier editing, and both
#: refuse the submitter. A `Procurement Manager` can verify a certificate but may
#: not decide a qualification, so the reviewer needs the compliance role.
REVIEWER_ROLES = ("Compliance Reviewer",)


def qualified_supplier(client, headers, code: str, name: str = "", *, reviewer_h: dict) -> str:
    """Create a supplier that is allowed to bid, and return its id.

    Three things are required and all three are enforced: an `active` supplier
    row, an approved certification, and a `qualified` qualification decision.

    `reviewer_h` is keyword-only and required. Certification verification and the
    qualification decision are both segregation-of-duties controls (VNT-025) and
    refuse the submitter, so a helper that let the submitter decide its own case
    would just produce a confusing 403 at some later line. Making it required
    means the identity split is visible in the call.
    """
    r = client.post("/api/v1/suppliers", json={"code": code, "name": name or f"{code} Ltd"},
                    headers=headers)
    assert r.status_code == 201, r.text
    sid = r.json()["data"]["id"]

    # Move draft -> active via the supplier PATCH (the lifecycle guard rejects
    # skipping states, so this has to be a real transition, not a direct write).
    res = client.patch(f"/api/v1/suppliers/{sid}", json={"status": "active"}, headers=headers)
    assert res.status_code == 200, res.text

    cert = client.post(f"/api/v1/suppliers/{sid}/certifications",
                       json={"name": "ISO 9001", "issuer": "TestBody"}, headers=headers)
    assert cert.status_code == 201, cert.text
    cid = cert.json()["data"]["id"]
    res = client.post(f"/api/v1/suppliers/{sid}/certifications/{cid}/verify", headers=reviewer_h)
    assert res.status_code == 200, res.text

    # A scorecard is the other half of the evidence. `submit_qual` only
    # auto-advances to `under_review` when there is >=1 verified certification
    # AND a grade of C or better, and `decide_qual` only accepts a qualification
    # that is under review — so a supplier cannot be qualified without one.
    # Dims are 0..1000 permille, and the key set is fixed (never defaulted).
    res = client.post(f"/api/v1/suppliers/{sid}/scorecard",
                      json={"dims": {"quality": 900, "delivery": 900, "price": 900,
                                     "compliance": 900, "responsiveness": 900}},
                      headers=headers)
    assert res.status_code == 201, res.text

    res = client.post(f"/api/v1/suppliers/{sid}/qualification/submit", headers=headers)
    assert res.status_code == 200, res.text
    dec = client.post(f"/api/v1/suppliers/{sid}/qualification/decide",
                      json={"decision": "qualified", "reason": "evidence complete"},
                      headers=reviewer_h)
    assert dec.status_code == 200, dec.text
    return sid


def rfq_line_ids(client, headers, rfq_id: str) -> list[str]:
    """The RFQ line ids a quote must cite."""
    r = client.get(f"/api/v1/rfqs/{rfq_id}", headers=headers)
    assert r.status_code == 200, r.text
    return [ln["id"] for ln in r.json()["data"].get("lines", [])]


def drain_notifications(client, headers) -> int:
    """Mark every visible notification read. Returns how many were drained.

    Onboarding legitimately emits its own notifications (certification verified,
    qualification decided), so a test that wants to assert an *exact* unread
    count for one business event has to clear the setup noise first. Asserting
    against a moving baseline is how badge tests rot.
    """
    drained = 0
    while True:
        page = client.get("/api/v1/notifications", params={"limit": 100, "unread": "true"},
                          headers=headers).json()
        rows = page.get("data") or []
        if not rows:
            return drained
        for row in rows:
            client.post(f"/api/v1/notifications/{row['id']}/read", headers=headers)
            drained += 1
        if not (page.get("pagination") or {}).get("hasMore"):
            return drained


def open_rfq_for_bid(client, headers, *, code: str, title: str, reviewer_h: dict,
                     currency: str = "INR", line_desc: str = "Widget",
                     quantity: int = 5) -> tuple[str, str, str]:
    """Onboard a qualified supplier, open an RFQ and send it. Returns
    `(rfq_id, rfq_line_id, supplier_id)` — everything a bid needs, and nothing
    past the point where a notification is emitted.

    Split out from `seed_rfq_award` so a caller can assert on the notification
    the *award* produces without the supplier-onboarding notifications already in
    the feed.
    """
    supplier = qualified_supplier(client, headers, f"S-{code}", f"{title} Supplier",
                                 reviewer_h=reviewer_h)
    created = client.post("/api/v1/rfqs", json={
        "code": code, "title": title, "currency": currency,
        "lines": [{"description": line_desc, "quantity": quantity}]},
        headers=headers)
    assert created.status_code == 201, created.text
    rfq_id = created.json()["data"]["id"]
    (line_id,) = rfq_line_ids(client, headers, rfq_id)
    sent = client.patch(f"/api/v1/rfqs/{rfq_id}/status", json={"status": "sent"}, headers=headers)
    assert sent.status_code == 200, sent.text
    return rfq_id, line_id, supplier


def submit_bid(client, headers, rfq_id: str, rfq_line_id: str, supplier_id: str, *,
               quantity: int = 5, unit_price_minor: int = 100,
               reason: str = "only bid") -> str:
    """Bid, evaluate, and award. Returns the quote id.

    `submit_quote` already moves `sent -> response` when the first bid lands, so
    each next state is *read* rather than assumed. Patching `response`
    unconditionally was a latent bug in several tests: the call returned 422 and
    nothing asserted on it, so a broken transition went unnoticed.
    """
    quote = client.post(f"/api/v1/rfqs/{rfq_id}/quotes", json={
        "supplier_id": supplier_id,
        "lines": [{"rfq_line_id": rfq_line_id, "quantity": quantity,
                   "unit_price_minor": unit_price_minor}]},
        headers=headers)
    assert quote.status_code == 201, quote.text
    quote_id = quote.json()["data"]["id"]

    current = client.get(f"/api/v1/rfqs/{rfq_id}", headers=headers).json()["data"]["status"]
    if current == "sent":
        responded = client.patch(f"/api/v1/rfqs/{rfq_id}/status", json={"status": "response"},
                                 headers=headers)
        assert responded.status_code == 200, responded.text
    current = client.get(f"/api/v1/rfqs/{rfq_id}", headers=headers).json()["data"]["status"]
    if current == "response":
        evaluated = client.patch(f"/api/v1/rfqs/{rfq_id}/status", json={"status": "evaluated"},
                                 headers=headers)
        assert evaluated.status_code == 200, evaluated.text
    award = client.post(f"/api/v1/rfqs/{rfq_id}/award",
                        json={"quote_id": quote_id, "reason": reason}, headers=headers)
    assert award.status_code == 201, award.text
    return quote_id


def seed_rfq_award(client, headers, *, code: str, title: str, reviewer_h: dict,
                   currency: str = "INR", line_desc: str = "Widget", quantity: int = 5,
                   unit_price_minor: int = 100, reason: str = "only bid") -> tuple[str, str]:
    """Take one RFQ all the way to an award. Returns `(rfq_id, quote_id)`.

    A single-bid award, set up legally: a qualified supplier, a quote that cites
    the RFQ line, and the RFQ currency. Notification and approval tests need an
    award to have happened, and none of them are about sourcing — so the sourcing
    preamble lives here once instead of being copy-pasted (and, before VNT-020
    and VNT-021, being wrong) in every module.
    """
    rfq_id, line_id, supplier = open_rfq_for_bid(
        client, headers, code=code, title=title, reviewer_h=reviewer_h,
        currency=currency, line_desc=line_desc, quantity=quantity)
    quote_id = submit_bid(client, headers, rfq_id, line_id, supplier,
                          quantity=quantity, unit_price_minor=unit_price_minor, reason=reason)
    return rfq_id, quote_id
