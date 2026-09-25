# One-time bulk wiring: prepend breadcrumb headers + normalize intra-docs links.
# Run: python scripts/add_brain_links.py
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MARK = "<!-- vantor-brain-link -->"

for p in sorted(ROOT.rglob("*.md")):
    if ".git" in p.parts or p.name == "masterdoc.txt":
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    if MARK in text:
        continue
    rel = p.parent
    # compute via os.path.relpath for reliability
    import os
    to_brain = os.path.relpath(ROOT / "docs" / "BRAIN.md", start=rel).replace(os.sep, "/")
    to_index = os.path.relpath(ROOT / "docs" / "README.md", start=rel).replace(os.sep, "/")
    if p.name == "BRAIN.md":
        header = f"{MARK}\n> Mirror index: [{p.parent.name and 'Docs index'}](README.md)\n\n"
        header = f"{MARK}\n> You are in the 🧠 **VANTOR Brain** — mirror index: [Docs index](README.md).\n\n"
    elif p == ROOT / "docs" / "README.md":
        header = f"{MARK}\n> 🧠 **Vantor Brain:** [BRAIN.md](BRAIN.md)\n\n"
    else:
        header = f"{MARK}\n> 🧠 **Vantor Brain:** [BRAIN.md]({to_brain}) · [Docs index]({to_index})\n\n"
    # normalize root-style intra-doc links inside docs/ subfolders: (docs/ -> (../
    if ROOT / "docs" in p.parents and p.parent != ROOT / "docs" and p.name != "BRAIN.md":
        text = text.replace("(docs/", "(../")
    p.write_text(header + text, encoding="utf-8")
    print("wired:", p.relative_to(ROOT))
