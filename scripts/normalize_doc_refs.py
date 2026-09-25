# Normalize root-style "`docs/..." text refs inside docs/ to relative "../...".
# Run: python scripts/normalize_doc_refs.py (one-time; safe to re-run)
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
count = 0
for p in sorted(DOCS.rglob("*.md")):
    if p.name == "BRAIN.md":
        continue
    text = p.read_text(encoding="utf-8")
    new = text.replace("`docs/", "`../").replace("(docs/", "(../")
    if new != text:
        p.write_text(new, encoding="utf-8")
        count += 1
        print("normalized:", p.relative_to(ROOT))
print("normalized files:", count)
