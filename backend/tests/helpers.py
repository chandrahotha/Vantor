"""Shared test helpers.

`category_id` columns are validated against real `categories` rows (there is no
FOREIGN KEY in this schema, so the API refuses a dangling id itself). Tests that
need a categorised PO must therefore create the category first and pass the id
it got back — passing a literal like "CAT-A" used to work only because the write
path accepted an id that pointed at nothing.
"""
from __future__ import annotations


def make_category(client, headers, code: str, name: str = "", parent_id: str = "") -> str:
    """Create a category and return its id, asserting the write succeeded."""
    r = client.post("/api/v1/catalog/categories",
                    json={"code": code, "name": name or code.title(), "parent_id": parent_id},
                    headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]
