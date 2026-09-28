"""Rasterize the brand marks in assets/brand/ into frontend/public/icons/.

There was no script here before, so the shipped PNGs were produced ad hoc and
could not be regenerated. This exists so the sidebar mark, the app icons and the
PWA assets all come from the same two canonical sources, and so a designer can
drop a new source file in and re-run this.

Two variants, both from the same V+orbit artwork:

  vantor-icon-source.png          the mark on its navy squircle
  vantor-icon-bg-less-source.png  the mark alone, transparent

The squircle is the app icon (favicons, PWA, apple-touch) because those are
rendered by the OS on an unknown background and need their own field. The
background-less mark is what the in-app sidebar uses: the sidebar is itself
near-black, and drawing a near-black squircle on a near-black surface leaves a
dark blob with a faint rounded edge rather than a legible mark.

Every output is trimmed to the artwork's real bounding box and then squared, so
a mark is not rendered small because of dead margin around it.

Usage:  python scripts/build_brand_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
OUT = ROOT / "frontend" / "public" / "icons"

# (source, output stem) — the squircle set keeps every existing filename so the
# manifest, layout metadata and any cached references stay valid.
SQUIRCLE = ("vantor-icon-source.png", None)
BGLESS = ("vantor-icon-bg-less-source.png", "mark-bgless")


def _square(im: Image.Image, size: int) -> Image.Image:
    """Trim transparent margin, then paste centred on a square canvas.

    Trimming is what makes the sidebar mark legible: the source has generous
    padding, and a naive resize renders the artwork at maybe 70% of the box.
    """
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
    return canvas.resize((size, size), Image.LANCZOS)


def _write(im: Image.Image, stem: str, name: str, sizes: list[int], square: bool) -> None:
    for size in sizes:
        out = im.resize((size, size), Image.LANCZOS) if square else im
        path = OUT / f"{stem}-{size}.png" if stem else OUT / name.format(size=size)
        out.save(path, "PNG", optimize=True)
        print(f"  {path.relative_to(ROOT)}  {size}x{size}  {path.stat().st_size / 1024:.1f} KB")


def build() -> int:
    if not BRAND.is_dir():
        print(f"missing {BRAND}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    print("squircle mark (app icons, PWA, manifest):")
    src = Image.open(BRAND / SQUIRCLE[0]).convert("RGBA")

    # favicons and the manifest marks come from the squircle at 4x then downsample,
    # because a browser rendering a 16px icon deserves the extra detail.
    for size in (16, 32):
        _write(_square(src, size * 4), None, "favicon-{size}.png", [size], True)
    for size in (64, 128, 256):
        _write(_square(src, size), "mark", "mark-{size}.png", [size], False)
    _write(_square(src, 512), None, "icon-{size}.png", [192, 512], True)

    # apple-touch must be opaque; iOS does not composite transparency.
    apple = _square(src, 180).convert("RGB")
    apple.save(OUT / "apple-touch-icon.png", "PNG", optimize=True)
    print(f"  frontend/public/icons/apple-touch-icon.png  180x180")

    print("background-less mark (in-app sidebar):")
    bg = Image.open(BRAND / BGLESS[0]).convert("RGBA")
    for size in (64, 128, 256):
        _write(_square(bg, size), BGLESS[1], f"{BGLESS[1]}-{{size}}.png", [size], False)

    return 0


if __name__ == "__main__":
    raise SystemExit(build())
