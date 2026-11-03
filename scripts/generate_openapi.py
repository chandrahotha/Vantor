#!/usr/bin/env python3
"""Generate the committed OpenAPI contract — both copies, from one source.

Run: python scripts/generate_openapi.py

The API contract used to be committed twice: `api/openapi.json` and
`api/openapi.yaml`. CI regenerated and diff-checked only the JSON, so the
YAML drifted silently — 80 of its 84 paths disagreed with the contract the
server actually serves, and the only references to it (a documentation page
and a changelog entry) described it as "generated at build", which no build
step did.

Two copies of one contract is a hazard, not a convenience: whichever copy is
not gated is a copy that rots. This script writes both from a single
`app.openapi()` call, so they cannot disagree with each other, and the CI
drift gate diffs both. The YAML is emitted with the same key ordering as the
JSON (`sort_keys=False`), because the ordering is what makes the two files
diffable by eye.

Environment:
  APP_ENV, DATABASE_URL  — honoured if already set; otherwise the script
                           falls back to the same SQLite/test defaults the
                           existing CI step used.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
API_DIR = ROOT / "api"

# The app reads its settings at import time. These are the defaults the
# committed contract was generated under; `setdefault` means a caller that
# already exported them keeps its own values.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")

# `app` is a package inside `backend/`, which is not installed — it is run
# from the source tree.
sys.path.insert(0, str(BACKEND))


def render() -> tuple[str, str]:
    """Return the (json, yaml) renderings of the live contract."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment problem
        raise SystemExit(
            "PyYAML is required to render api/openapi.yaml.\n"
            "Install it with: pip install pyyaml"
        ) from exc

    from app.main import app

    contract = app.openapi()
    # `json.dump(..., indent=2)` leaves no trailing newline; the committed
    # JSON has none, and adding one would make the drift gate report a
    # difference on every run.
    as_json = json.dumps(contract, indent=2)
    # `sort_keys=False` preserves FastAPI's own ordering, which is what the
    # committed YAML already uses.
    as_yaml = yaml.dump(contract, sort_keys=False, default_flow_style=False)
    return as_json, as_yaml


def main() -> int:
    as_json, as_yaml = render()
    API_DIR.mkdir(parents=True, exist_ok=True)
    (API_DIR / "openapi.json").write_text(as_json, encoding="utf-8")
    (API_DIR / "openapi.yaml").write_text(as_yaml, encoding="utf-8")
    paths = len(json.loads(as_json).get("paths", {}))
    print(f"wrote api/openapi.json and api/openapi.yaml ({paths} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
