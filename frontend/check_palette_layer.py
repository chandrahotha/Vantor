"""Audit the theming layer in globals.css.

Three things a stylesheet can get wrong that no typechecker sees:

1. **Custom property cycles.** `--primary: var(--primary)` is invalid at
   computed-value time; the property becomes unset and silently inherits the
   `:root` default. The app looks half-themed and the CSS looks correct.
2. **Dangling references.** A `var(--x)` with no definition resolves to
   nothing, so the declaration using it is dropped.
3. **Contrast.** "Ensure every palette passes WCAG AA" is a claim that has to be
   measured, not asserted.

Run: python check_palette_layer.py
"""
from __future__ import annotations

import colorsys
import pathlib
import re
import sys

CSS = pathlib.Path(__file__).with_name("app") / "globals.css"
PALETTES = ["graphite", "emerald", "sapphire", "amber", "obsidian"]

# The block that declares a palette's tokens, per palette and mode.
BLOCK_RE = re.compile(r"^\[data-palette=\"(?P<key>[a-z]+)\"\](?P<dark>\[data-theme=\"dark\"\])?")
DECL_RE = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(.+?);\s*$")
VAR_RE = re.compile(r"var\(\s*(--[a-z0-9-]+)")

failures: list[str] = []
notes: list[str] = []


def blocks() -> dict[tuple[str, bool], dict[str, str]]:
    """(palette, is_dark) -> {token: value} for the palette declaration blocks."""
    out: dict[tuple[str, bool], dict[str, str]] = {}
    current: tuple[str, bool] | None = None
    for line in CSS.read_text(encoding="utf-8").splitlines():
        m = BLOCK_RE.match(line)
        if m:
            current = (m.group("key"), bool(m.group("dark")))
            out.setdefault(current, {})
            continue
        if current and line.strip() == "}":
            current = None
            continue
        if current:
            d = DECL_RE.match(line)
            if d:
                out[current][d.group(1)] = d.group(2).strip()
    return out


def shared_tokens() -> dict[str, str]:
    """Tokens declared in `:root` and the dark override, outside any palette."""
    out: dict[str, str] = {}
    dark: dict[str, str] = {}
    mode: str | None = None
    for line in CSS.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(':root'):
            mode = "light"
            continue
        if s.startswith('[data-theme="dark"]') or s == ".dark {":
            mode = "dark"
            continue
        if s == "}":
            mode = None
            continue
        if mode:
            d = DECL_RE.match(line)
            if d:
                (out if mode == "light" else dark)[d.group(1)] = d.group(2).strip()
    out["__dark__"] = dark  # type: ignore[assignment]
    return out


# --- 1. cycles -------------------------------------------------------------
def check_cycles(all_rules: list[tuple[str, dict[str, str]]]) -> None:
    for selector, decls in all_rules:
        for token, value in decls.items():
            for ref in VAR_RE.findall(value):
                if ref == token:
                    failures.append(
                        f"cycle: `{selector}` declares {token}: var({token}) — "
                        "invalid at computed-value time, silently inherits the root value"
                    )


# --- 2. dangling references ------------------------------------------------
def check_dangling(defined: set[str], all_rules: list[tuple[str, dict[str, str]]]) -> None:
    for selector, decls in all_rules:
        for token, value in decls.items():
            for ref in VAR_RE.findall(value):
                if ref not in defined and not ref.startswith("--font"):
                    failures.append(f"dangling: `{selector}` {token} references undefined {ref}")


# --- 3. contrast -----------------------------------------------------------
def parse_hex(value: str) -> tuple[int, int, int] | None:
    v = value.strip().lower()
    if not v.startswith("#"):
        return None
    h = v[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def adjust(hexv: str, *, lighten: float) -> str:
    """Lighten (amount>0) or darken (amount<0) toward white/black in HLS space."""
    rgb = parse_hex(hexv)
    if rgb is None:
        return hexv
    h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
    l = max(0.0, min(1.0, l + lighten))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def check_contrast(pal: dict[tuple[str, bool], dict[str, str]]) -> None:
    # Pairs that actually carry text in this UI, with the AA threshold for each.
    # Normal text is 4.5:1; large text and UI component boundaries are 3:1.
    pairs = [
        ("--text-primary", "--bg-base", 4.5, "body text on page"),
        ("--text-primary", "--bg-surface", 4.5, "body text on card/panel"),
        ("--text-primary", "--bg-elevated", 4.5, "body text on elevated surface"),
        ("--text-secondary", "--bg-base", 4.5, "secondary text on page"),
        ("--text-secondary", "--bg-surface", 4.5, "secondary text on card"),
        ("--text-muted", "--bg-base", 4.5, "muted text (column headers, hints)"),
        ("--text-muted", "--bg-surface", 4.5, "muted text on card"),
        ("--primary-fg", "--primary", 4.5, "label on a primary button"),
        ("--primary", "--bg-surface", 3.0, "primary text/links on surface"),
        # `--accent` paints large gradient fills (a 64px mark, a CTA), where the
        # 3:1 non-text threshold does not apply. What must meet 3:1 is
        # `--accent-ui`: the sidebar's active-route bar and any accent text.
        ("--accent-ui", "--bg-surface", 3.0, "accent small marks on surface"),
        ("--accent-ui", "--bg-base", 3.0, "accent small marks on page"),
        ("--text-primary", "--bg-sunken", 4.5, "text on sunken surface"),
        ("--side-ink", "--side-bg", 4.5, "sidebar nav label"),
        ("--side-ink-strong", "--side-bg", 4.5, "sidebar user chip"),
    ]

    for key in PALETTES:
        for is_dark in (False, True):
            toks = pal.get((key, is_dark))
            if toks is None:
                failures.append(f"missing block: [data-palette={key}] dark={is_dark}")
                continue
            mode = "dark" if is_dark else "light"
            for fg, bg, threshold, what in pairs:
                f, b = toks.get(fg), toks.get(bg)
                if not f or not b:
                    failures.append(f"{key}/{mode}: {fg} or {bg} not defined")
                    continue
                fr, br = parse_hex(f), parse_hex(b)
                if fr is None or br is None:
                    failures.append(f"{key}/{mode}: {fg}/{bg} not plain hex ({f}/{b})")
                    continue
                cr = ratio(fr, br)
                if cr < threshold:
                    failures.append(
                        f"{key}/{mode}: {what} {fg} on {bg} = {cr:.2f}:1 "
                        f"(needs {threshold}:1)  {f} on {b}"
                    )


def main() -> int:
    pal = blocks()
    shared = shared_tokens()

    # Every palette block must declare the full required token set.
    required = [
        "--bg-base", "--bg-elevated", "--bg-surface", "--bg-sunken",
        "--primary", "--primary-hover", "--primary-soft", "--primary-fg",
        "--accent", "--accent-hover",
        "--text-primary", "--text-secondary", "--text-muted", "--text-inverse",
        "--border", "--border-strong", "--divider",
        "--success", "--warning", "--danger", "--info", "--neutral",
        "--shadow-sm", "--shadow-md", "--shadow-lg",
        "--focus-ring", "--accent-ui",
        "--side-bg", "--side-ink", "--side-ink-strong", "--side-line",
    ]
    for key in PALETTES:
        for is_dark in (False, True):
            toks = pal.get((key, is_dark), {})
            missing = [t for t in required if t not in toks]
            if missing:
                failures.append(f"{key}/{'dark' if is_dark else 'light'}: missing {missing}")

    # Status + chart tokens must be identical across palettes, and defined.
    for token in [f"--status-{s}" for s in
                  ("draft", "in-review", "pending", "approved", "rejected",
                   "sealed", "expired", "at-risk", "non-compliant")] + \
                 [f"--chart-{i}" for i in range(1, 9)]:
        if token not in shared:
            failures.append(f"shared token {token} is not defined in :root")

    all_rules = [(f'[data-palette="{k}"]{"+dark" if d else ""}', v) for (k, d), v in pal.items()]
    defined = set(shared) | {t for v in pal.values() for t in v} | set(shared["__dark__"])  # type: ignore[arg-type]
    check_cycles(all_rules)
    check_dangling(defined, all_rules)
    check_contrast(pal)

    print(f"palette blocks parsed: {len(pal)} (expected {len(PALETTES) * 2})")
    print(f"shared root tokens:    {len(shared) - 1}")
    for n in notes:
        print(f"note  {n}")
    for f in failures:
        print(f"FAIL  {f}")
    if failures:
        print(f"\n{len(failures)} problem(s)")
        return 1
    print("\nOK — no cycles, no dangling tokens, all contrast pairs meet their threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
