#!/usr/bin/env python3
"""Documentation link gate — no broken links, no orphan pages.

Run: python scripts/verify_doc_links.py

The previous gate required the string "BRAIN.md" to appear in every markdown
file in the repository. That is a convention check, not a quality check: it
passed while links pointed at files that did not exist, and it forced an
internal documentation convention onto the public READMEs, which are the
first thing a visitor reads and the last thing that should be carrying
process machinery.

This gate checks the things that actually matter for a public repository:

1. **Every relative link resolves.** A link to a file that does not exist is
   a broken promise in the rendered page.
2. **No orphan pages.** Every document under `docs/` is reachable from the
   documentation index by following relative links.
3. **The documentation index is reachable.** The top-level and per-module
   READMEs link to it, so the docs are discoverable from where a reader
   lands.
4. **The docs tree keeps its central index.** Documents under `docs/` link
   back to `BRAIN.md`. The convention stays where it belongs — inside the
   documentation tree — and off the public landing pages.

Exit code is non-zero when any check fails, so it can gate CI.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DOCS_INDEX = DOCS / "README.md"
BRAIN = DOCS / "BRAIN.md"

#: The public landing pages. Each must point a reader at the docs index.
PUBLIC_READMES = [
    "README.md",
    "backend/README.md",
    "frontend/README.md",
    "worker/README.md",
    "android/README.md",
]

#: `[text](url)` and `![alt](url)`. The URL may be wrapped in angle
#: brackets, and may carry a `#fragment` or a `?query`.
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")

#: Directories that are never part of the published documentation.
SKIP_DIRS = {
    ".git", "node_modules", ".next", "dist", "build", "__pycache__", ".venv",
    "venv", "vendor", "target", ".opencode", ".pytest_cache", ".kilo",
}


def markdown_files() -> list[pathlib.Path]:
    """Every tracked markdown file, in stable order."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        out = None
    if out is not None and out.returncode == 0 and out.stdout.strip():
        names = [line for line in out.stdout.splitlines() if line.strip()]
        paths = [ROOT / name for name in names]
        return [p for p in paths if p.exists() and not (SKIP_DIRS & set(p.parts))]
    # No git available: fall back to a filesystem walk.
    return sorted(
        p for p in ROOT.rglob("*.md")
        if not (SKIP_DIRS & set(p.parts))
    )


def is_external(url: str) -> bool:
    """True for links that are not local file references."""
    lowered = url.lower()
    return (
        lowered.startswith(("http://", "https://", "mailto:", "tel:", "ftp://"))
        or url.startswith("#")
        or url.startswith("//")
    )


def local_targets(path: pathlib.Path) -> list[str]:
    """The local file paths `path` links to, or [] for external links."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[str] = []
    for raw in LINK_RE.findall(text):
        url = unquote(raw.strip())
        if not url or is_external(url):
            continue
        # Drop the fragment and query: the file is what has to exist.
        url = url.split("#", 1)[0].split("?", 1)[0]
        if not url:
            continue
        if url.startswith("/"):
            out.append(str(ROOT / url.lstrip("/")))
        else:
            out.append(str((path.parent / url)))
    return out


def resolves(target: str) -> bool:
    """True when a link target names an existing file or a documented directory."""
    p = pathlib.Path(target)
    if p.exists():
        return True
    # A link to a directory is fine when that directory has a README.
    return p.is_dir() and (p / "README.md").exists()


def check_links(files: list[pathlib.Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        for target in local_targets(path):
            normalised = os.path.normpath(target)
            # Links that escape the repository are GitHub-relative URLs
            # (`../../issues`), not files on disk.
            try:
                pathlib.Path(normalised).relative_to(ROOT)
            except ValueError:
                continue
            if not resolves(normalised):
                problems.append(
                    f"{rel}: broken link -> "
                    f"{pathlib.Path(normalised).relative_to(ROOT).as_posix()}"
                )
    return problems


def reachable_from(index: pathlib.Path) -> set[pathlib.Path]:
    """Every local markdown file reachable from `index` by relative links."""
    seen: set[pathlib.Path] = set()
    queue = [index]
    while queue:
        current = queue.pop()
        if current in seen or not current.exists():
            continue
        seen.add(current)
        for target in local_targets(current):
            candidate = pathlib.Path(os.path.normpath(target))
            if candidate.suffix == ".md" and candidate.exists():
                queue.append(candidate)
    return seen


def check_no_orphans(files: list[pathlib.Path]) -> list[str]:
    problems: list[str] = []
    reachable = reachable_from(DOCS_INDEX)
    for path in files:
        try:
            path.relative_to(DOCS)
        except ValueError:
            continue
        if path == DOCS_INDEX:
            continue
        if path not in reachable:
            problems.append(
                f"{path.relative_to(ROOT).as_posix()}: not reachable from "
                f"docs/README.md"
            )
    return problems


def check_index_reachable() -> list[str]:
    problems: list[str] = []
    for rel in PUBLIC_READMES:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "docs/README.md" not in text:
            problems.append(f"{rel}: does not link to docs/README.md")
    return problems


def check_backlinks(files: list[pathlib.Path]) -> list[str]:
    """Documents in the docs tree link back to the central index."""
    problems: list[str] = []
    for path in files:
        try:
            path.relative_to(DOCS)
        except ValueError:
            continue
        if path.name == "BRAIN.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "BRAIN.md" not in text:
            problems.append(
                f"{path.relative_to(ROOT).as_posix()}: does not link back to "
                f"docs/BRAIN.md"
            )
    return problems


def main() -> int:
    files = markdown_files()
    problems: list[str] = []
    problems += check_links(files)
    problems += check_no_orphans(files)
    problems += check_index_reachable()
    problems += check_backlinks(files)

    print(f"checked={len(files)} problems={len(problems)}")
    for p in problems:
        print("FAIL", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
