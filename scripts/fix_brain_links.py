"""Brain-link repair — prepend the standard header to any doc missing one.

Run: python scripts/fix_brain_links.py
Verifies with: python scripts/verify_brain_links.py

The verifier only requires the string "BRAIN.md" to appear in every markdown
doc outside the vendored spec bundle. This writes the canonical header so the
link is real rather than a token, and it computes the correct relative depth
per file so the link actually resolves.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRAIN = ROOT / "docs" / "BRAIN.md"
DOCS_INDEX = ROOT / "docs" / "README.md"

SKIP = {"BRAIN.md"}
SKIP_DIRS = {".git", "node_modules", ".next", "dist", "build", "__pycache__",
             ".venv", "venv", "vendor", "target", ".opencode", ".pytest_cache"}

MARKER = "<!-- vantor-brain-link -->"
HEAD = "> \U0001f9e0 **Vantor Brain:** [BRAIN.md]({brain}) · [Docs index]({index})"


def relative(path: pathlib.Path, target: pathlib.Path) -> str:
    """POSIX-style relative path from `path`'s directory to `target`."""
    import os
    rel = os.path.relpath(target, path.parent).replace("\\", "/")
    return rel


def header_for(path: pathlib.Path) -> str:
    return f"{MARKER}\n{HEAD.format(brain=relative(path, BRAIN), index=relative(path, DOCS_INDEX))}\n\n"


def main() -> int:
    targets = sorted(p for p in ROOT.rglob("*.md")
                     if p.name not in SKIP and not (SKIP_DIRS & set(p.parts)))
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
