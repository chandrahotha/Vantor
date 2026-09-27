"""Repair mojibake introduced by a Windows PowerShell write.

PowerShell 5.1's `Set-Content -Encoding UTF8` adds a BOM and, when the console
code page is not UTF-8, can read the source as cp1252 and write the result back
as UTF-8 -- turning every em dash into three characters and prepending a BOM.

This undoes both. Run: python scripts/repair_encoding.py [paths...]
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The cp1252 rendering of the UTF-8 bytes for the characters this codebase
# actually uses. Longest-first so the 3-byte sequences win over their prefixes.
MOJIBAKE = {
    "—": "—",  # em dash
    "–": "–",  # en dash
    "…": "…",  # ellipsis
    "’": "’",  # right single quote
    "“": "“",  # left double quote
    "”": "”",  # right double quote
    "→": "→",  # right arrow
    "←": "←",  # left arrow
    "•": "•",  # bullet
    "·": "·",   # middle dot
    "°": "°",   # degree
    "é": "é",
    "ü": "ü",
    "ö": "ö",
    "ä": "ä",
    "ñ": "ñ",
    "£": "£",
    "©": "©",
    "®": "®",
    " ": " ",   # non-breaking space
}
ORDER = sorted(MOJIBAKE, key=len, reverse=True)


def repair(path: pathlib.Path) -> tuple[int, bool]:
    raw = path.read_bytes()
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    before = text
    for bad in ORDER:
        text = text.replace(bad, MOJIBAKE[bad])
    changed = text != before or had_bom
    if changed:
        path.write_bytes(text.encode("utf-8"))
    return text.count("—"), changed


def main(argv: list[str]) -> int:
    targets = [pathlib.Path(a) if pathlib.Path(a).is_absolute() else ROOT / a for a in argv[1:]]
    if not targets:
        targets = [p for p in ROOT.rglob("*")
                   if p.is_file() and p.suffix in {".py", ".md", ".ts", ".tsx", ".css", ".yml", ".yaml", ".json", ".sh", ".ps1", ".mjs"}
                   and not ({"node_modules", ".next", ".git", ".kilo", "mypy_cache",
                             ".pytest_cache", ".ruff_cache", "__pycache__", "11-specs-06-10"} & set(p.parts))]
    fixed = 0
    for p in targets:
        if not p.exists():
            print("MISSING:", p)
            continue
        _, changed = repair(p)
        if changed:
            fixed += 1
            print("REPAIRED:", p.relative_to(ROOT) if ROOT in p.parents else p)
    print(f"scanned={len(targets)} repaired={fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
