# Link verifier — every markdown doc must connect to the Brain.
# Run: python scripts/verify_brain_links.py
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP = {"masterdoc.txt"}
failures = []
mds = sorted(p for p in ROOT.rglob("*.md") if p.name not in SKIP and ".git" not in p.parts)
for p in mds:
    if p.name in ("BRAIN.md",):
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    if "BRAIN.md" not in text:
        failures.append(str(p.relative_to(ROOT)))
print(f"checked={len(mds)} failures={len(failures)}")
for f in failures:
    print("MISSING BRAIN LINK:", f)
sys.exit(1 if failures else 0)
