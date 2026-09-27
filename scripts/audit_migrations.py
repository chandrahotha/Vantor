"""Final audit: the migration chain, its single head, and that each `upgrade()`
is a real callable. Runs without a database.

The PostgreSQL *effects* of these migrations are still unverified here — that
needs PG_TEST_DATABASE_URL — so this checks the things that can be checked
offline: that the chain is linear with exactly one head, that every revision
declares both directions, and that each module imports cleanly.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # repo root, not scripts/
VERSIONS = ROOT / "backend" / "alembic" / "versions"

if not VERSIONS.is_dir():
    print(f"FAIL no versions directory at {VERSIONS}")
    sys.exit(1)

problems: list[str] = []
revisions: dict[str, str | None] = {}
mods: dict[str, object] = {}

for path in sorted(VERSIONS.glob("*.py")):
    if path.name.startswith("_"):
        continue
    spec = importlib.util.spec_from_file_location(f"_audit_{path.stem}", path)
    if not (spec and spec.loader):
        problems.append(f"{path.name}: not importable")
        continue
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        problems.append(f"{path.name}: import failed: {exc!r}")
        continue
    rev = getattr(module, "revision", None)
    down = getattr(module, "down_revision", None)
    if not rev:
        problems.append(f"{path.name}: no revision")
        continue
    if rev in revisions:
        problems.append(f"{path.name}: duplicate revision {rev}")
    revisions[rev] = down
    mods[rev] = module
    for direction in ("upgrade", "downgrade"):
        if not callable(getattr(module, direction, None)):
            problems.append(f"{path.name}: missing {direction}()")
    print(f"  {path.stem:36} rev={rev:28} down={down}")

# Linear chain, exactly one head.
referenced = {d for d in revisions.values() if d}
heads = [r for r in revisions if r not in referenced]
if len(heads) != 1:
    problems.append(f"expected exactly one head, found {heads}")
else:
    print(f"\nhead: {heads[0]}")

# Walk the chain from head to base, checking each link exists.
if len(heads) == 1:
    node = heads[0]
    seen = []
    while node is not None:
        if node in seen:
            problems.append(f"cycle in the migration chain at {node}")
            break
        seen.append(node)
        node = revisions.get(node)
        if node is not None and node not in revisions:
            problems.append(f"down_revision {node!r} does not exist")
            break
    print(f"chain length: {len(seen)} (head -> base)")

for p in problems:
    print(f"FAIL {p}")
if problems:
    print(f"\n{len(problems)} problem(s)")
    sys.exit(1)
print("\nOK - linear chain, one head, both directions present, all modules import")
