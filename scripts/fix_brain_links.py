"""Brain-link repair — restore the docs-tree header on a document missing one.

Run: python scripts/fix_brain_links.py
Verifies with: python scripts/verify_doc_links.py

`docs/` is a documentation tree with its own central index, so every page in
it links back to `docs/BRAIN.md`. This writes that header, computing the
correct relative depth per file so the link actually resolves.

It deliberately does **not** touch the top-level or per-module READMEs.
Those are the public landing pages; the documentation tree's navigation
convention is not something a visitor to a GitHub repository should have to
read past. The gate in `verify_doc_links.py` checks that the READMEs link to
`docs/README.md` instead.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BRAIN = DOCS / "BRAIN.md"
DOCS_INDEX = DOCS / "README.md"

SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "__pycache__",
             ".venv", "venv", "vendor", "target", ".opencode", ".pytest_cache",
             ".kilo"}

MARKER = "<!-- vantor-brain-link -->"
HEAD = "> \U0001f9e0 **Vantor Brain:** [BRAIN.md]({brain}) · [Docs index]({index})"


def relative(path: pathlib.Path, target: pathlib.Path) -> str:
    """POSIX-style relative path from `path`'s directory to `target`."""
    return os.path.relpath(target, path.parent).replace("\\", "/")


def header_for(path: pathlib.Path) -> str:
    return f"{MARKER}\n{HEAD.format(brain=relative(path, BRAIN), index=relative(path, DOCS_INDEX))}\n\n"


def main() -> int:
    targets = sorted(
        p for p in DOCS.rglob("*.md")
        if p.name != "BRAIN.md" and not (SKIP_DIRS & set(p.parts))
    )
    changed = []
    for p in targets:
        text = p.read_text(encoding="utf-8", errors="replace")
        if "BRAIN.md" in text:
            continue
        p.write_text(header_for(p) + text, encoding="utf-8")
        changed.append(str(p.relative_to(ROOT)))

    print(f"scanned={len(targets)} repaired={len(changed)}")
    for c in changed:
        print("REPAIRED:", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
