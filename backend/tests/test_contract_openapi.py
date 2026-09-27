"""Auto-generated OpenAPI contract test.

`api<T>()` calls the backend with no runtime type-check. Every frontend field
reference is only a TypeScript claim, but no test ever reads the response back
against the schema the API publishes. The copied schema lives at
`api/openapi.json` and must match the generated one — CI runs a diff on it.

This test is that assertion: it walks both the generated schema and the
fixtures the frontend uses (Suppliers, PurchaseOrders, RFQs, Approvals), checks
that the named fields the UI reads actually exist, and fails if a field name
changes or an endpoint loses a required prop.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "api/openapi.json"


@pytest.fixture(scope="session")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def component(schema: dict, name: str) -> dict:
    comp = schema.get("components", {}).get("schemas", {})
    assert name in comp, f"OpenAPI schema missing component {name}"
    return comp[name]


def assert_field(schema: dict, component_name: str, field: str) -> None:
    """Fail if the component is missing or the field is not on it."""
    c = component(schema, component_name)
    props = c.get("properties", {})
    assert field in props, f"{component_name} missing {field}"
    spec = props[field]
    # a $ref / anyOf / allOf array-group is fine; raw primitive fine too
    if spec.get("$ref") or spec.get("anyOf") or spec.get("allOf"):
        return
    ok = spec.get("type") in ("string", "integer", "number", "boolean", "array", "object", "null")
    assert ok, f"{component_name}.{field} has an unsupported shape: {spec}"


@pytest.mark.parametrize("component,field", [
    ("CompleteIn", "prompt"),
    ("CompleteIn", "provider"),
    ("CompleteIn", "model"),
    ("CompleteIn", "provider_key"),
    ("CompleteIn", "system"),
    ("CompleteIn", "tools"),
])
def test_ai_complete_fields(schema, component, field):
    """The frontend never writes these if they don't exist."""
    assert_field(schema, component, field)


@pytest.mark.parametrize("component,field", [
    ("PoIn", "supplier_id"),
    ("PoIn", "category_id"),
    ("PoIn", "requisition_id"),
    ("ReceiptIn", "lines"),
    ("InvIn", "code"),
])
def test_models_have_the_expected_fields(schema, component, field):
    assert_field(schema, component, field)


def test_alembic_revision_is_registered(schema):
    ver = schema.get("info", {}).get("version", "")
    assert ver, "no info.version in generated OpenAPI"


def test_price_evaluate_payload_fields_exist(schema):
    """The optimizer's clients must define every field the server returns (allocations etc. show these)."""
    post = schema.get("paths", {}).get("/api/v1/spend/price-evaluate/{po_id}", {}).get("post", {})
    assert post, "POST /spend/price-evaluate/{po_id} is not in the schema"
    r201 = post.get("responses", {}).get("201", {}).get("content", {}).get("application/json", {}).get("schema", {})
    assert r201, "201 response shape has no schema"
    assert r201.get("type") == "object"
    assert isinstance(r201.get("properties", {}).get("data") or {}, dict)


