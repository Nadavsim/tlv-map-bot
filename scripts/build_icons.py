"""Regenerates the app icons (PWA 192/512, apple-touch 180) in the Enamel palette.

    python -m scripts.build_icons                 # write the icons (DESIGN below)
    python -m scripts.build_icons --sheet out.png # contact sheet of every concept

Pure standard library (no Pillow / ImageMagick needed): shapes are rasterised
from signed-distance functions with analytic anti-aliasing and written as PNGs
with zlib. Each concept is a list of shapes drawn in order on an enamel-blue
square. The favicon in frontend/index.html is an inline SVG of the same mark -
keep them in step.
"""

import struct
import sys
import zlib
from pathlib import Path

ICONS = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"

BLUE = (0x0B, 0x57, 0xA4)
WHITE = (0xFF, 0xFF, 0xFF)
LEMON = (0xFF, 0xCB, 0x3D)
MELON = (0xB9, 0x1F, 0x47)

# Shapes in unit coordinates (0..1), painted in order:
#   ("rrect", cx, cy, half_w, half_h, radius, colour)   ("circle", cx, cy, r, colour)
#   ("ring", cx, cy, outer_r, inner_r, colour)
CONCEPTS = {
    # Tel Aviv's White City: stacked curved Bauhaus balconies under a lemon sun.
    "balconies": [
        ("circle", 0.74, 0.27, 0.075, LEMON),
        ("rrect", 0.46, 0.40, 0.24, 0.05, 0.05, WHITE),
        ("rrect", 0.54, 0.53, 0.24, 0.05, 0.05, WHITE),
        ("rrect", 0.46, 0.66, 0.24, 0.05, 0.05, WHITE),
        ("rrect", 0.5, 0.79, 0.30, 0.025, 0.025, WHITE),
    ],
    # Coffee: Tel Aviv runs on it. A cup with a handle, a saucer and two steam wisps.
    "cup": [
        ("rrect", 0.43, 0.30, 0.018, 0.06, 0.018, LEMON),
        ("rrect", 0.55, 0.27, 0.018, 0.06, 0.018, LEMON),
        ("rrect", 0.47, 0.58, 0.22, 0.17, 0.11, WHITE),
        ("ring", 0.70, 0.56, 0.115, 0.06, WHITE),
        ("rrect", 0.5, 0.78, 0.31, 0.03, 0.03, WHITE),
    ],
    # Food: a plate with a fork and a spoon.
    "plate": [
        ("circle", 0.5, 0.5, 0.27, WHITE),
        ("ring", 0.5, 0.5, 0.20, 0.185, BLUE),
        ("circle", 0.5, 0.5, 0.06, LEMON),
        ("rrect", 0.14, 0.62, 0.016, 0.20, 0.016, WHITE),
        ("rrect", 0.105, 0.34, 0.012, 0.075, 0.012, WHITE),
        ("rrect", 0.14, 0.34, 0.012, 0.075, 0.012, WHITE),
        ("rrect", 0.175, 0.34, 0.012, 0.075, 0.012, WHITE),
        ("rrect", 0.14, 0.42, 0.045, 0.014, 0.014, WHITE),
        ("rrect", 0.86, 0.66, 0.016, 0.17, 0.016, WHITE),
        ("rrect", 0.86, 0.36, 0.04, 0.07, 0.04, WHITE),
    ],
}
DESIGN = "cup"


def _round_rect_sd(x, y, cx, cy, hw, hh, r):
    """Signed distance to a rounded rectangle (negative inside)."""
    qx, qy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    outside = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** 0.5
    return outside + min(max(qx, qy), 0) - r


def _circle_sd(x, y, cx, cy, r):
    return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - r


def _cover(sd, px):
    """Anti-aliased coverage from a signed distance (in unit coordinates)."""
    return max(0.0, min(1.0, 0.5 - sd * px))


def _coverage(shape, x, y, size):
    kind = shape[0]
    if kind == "rrect":
        _, cx, cy, hw, hh, r, _c = shape
        return _cover(_round_rect_sd(x, y, cx, cy, hw, hh, r), size)
    if kind == "circle":
        _, cx, cy, r, _c = shape
        return _cover(_circle_sd(x, y, cx, cy, r), size)
    _, cx, cy, ro, ri, _c = shape  # ring
    return _cover(_circle_sd(x, y, cx, cy, ro), size) * (1 - _cover(_circle_sd(x, y, cx, cy, ri), size))


def render(size: int, rounded_square: bool, shapes) -> bytes:
    rows = []
    for j in range(size):
        row = bytearray([0])  # PNG filter type 0
        y = (j + 0.5) / size
        for i in range(size):
            x = (i + 0.5) / size
            alpha = _cover(_round_rect_sd(x, y, 0.5, 0.5, 0.5, 0.5, 0.22), size) if rounded_square else 1.0
            r, g, b = BLUE
            for shape in shapes:
                c = _coverage(shape, x, y, size)
                col = shape[-1]
                r, g, b = (r + (col[0] - r) * c, g + (col[1] - g) * c, b + (col[2] - b) * c)
            row += bytes((round(r), round(g), round(b), round(alpha * 255)))
        rows.append(bytes(row))
    return b"".join(rows)


def png_bytes(width: int, height: int, raw_rows: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw_rows, 9))
        + chunk(b"IEND", b"")
    )


def png(size: int, rounded_square: bool, shapes) -> bytes:
    return png_bytes(size, size, render(size, rounded_square, shapes))


def contact_sheet(path: Path, size: int = 256) -> None:
    """Every concept side by side on a light page, for choosing between them."""
    gap, names = 24, list(CONCEPTS)
    tiles = [render(size, True, CONCEPTS[n]) for n in names]
    width = len(names) * size + (len(names) + 1) * gap
    height = size + 2 * gap
    page = (0xED, 0xF2, 0xF0, 255)
    out = bytearray()
    for y in range(height):
        out.append(0)
        for t_index in range(len(names) + 1):
            out += bytes(page) * gap
            if t_index == len(names):
                break
            ty = y - gap
            if 0 <= ty < size:
                row = tiles[t_index][ty * (size * 4 + 1) + 1 : (ty + 1) * (size * 4 + 1)]
                for k in range(size):
                    r, g, b, a = row[k * 4 : k * 4 + 4]
                    a /= 255
                    out += bytes((round(r * a + page[0] * (1 - a)), round(g * a + page[1] * (1 - a)), round(b * a + page[2] * (1 - a)), 255))
            else:
                out += bytes(page) * size
    path.write_bytes(png_bytes(width, height, bytes(out)))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--sheet":
        contact_sheet(Path(sys.argv[2]))
        print("wrote", sys.argv[2], "-", ", ".join(CONCEPTS))
    else:
        # iOS rounds apple-touch-icon itself and renders transparency as black, so
        # that one is a full-bleed opaque square; the PWA icons keep rounded corners.
        for name, size, rounded in (("icon-512.png", 512, True), ("icon-192.png", 192, True), ("apple-touch-icon.png", 180, False)):
            (ICONS / name).write_bytes(png(size, rounded, CONCEPTS[DESIGN]))
            print("wrote", name)
