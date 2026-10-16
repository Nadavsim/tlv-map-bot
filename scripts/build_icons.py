"""Regenerates the app icons (PWA 192/512, apple-touch 180) in the Enamel palette.

    python -m scripts.build_icons

Pure standard library (no Pillow / ImageMagick needed): shapes are rasterised
from signed-distance functions with analytic anti-aliasing and written as PNGs
with zlib. The mark: an enamel-blue square, a white street-sign plate, and a
"you are here" target (blue ring and dot). The favicon in
frontend/index.html is the same mark as an inline SVG - keep them in step.
"""

import struct
import zlib
from pathlib import Path

ICONS = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"

BLUE = (0x0B, 0x57, 0xA4)
WHITE = (0xFF, 0xFF, 0xFF)


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


def render(size: int, rounded_square: bool) -> bytes:
    rows = []
    for j in range(size):
        row = bytearray([0])  # PNG filter type 0
        y = (j + 0.5) / size
        for i in range(size):
            x = (i + 0.5) / size
            # background: rounded square (transparent corners) or full bleed
            if rounded_square:
                alpha = _cover(_round_rect_sd(x, y, 0.5, 0.5, 0.5, 0.5, 0.22), size)
            else:
                alpha = 1.0
            r, g, b = BLUE
            # white sign plate
            c = _cover(_round_rect_sd(x, y, 0.5, 0.5, 0.33, 0.25, 0.09), size)
            r, g, b = (r + (WHITE[0] - r) * c, g + (WHITE[1] - g) * c, b + (WHITE[2] - b) * c)
            # target ring: outer radius .15, inner .095
            ring = _cover(_circle_sd(x, y, 0.5, 0.5, 0.15), size) * (1 - _cover(_circle_sd(x, y, 0.5, 0.5, 0.095), size))
            r, g, b = (r + (BLUE[0] - r) * ring, g + (BLUE[1] - g) * ring, b + (BLUE[2] - b) * ring)
            # solid centre
            dot = _cover(_circle_sd(x, y, 0.5, 0.5, 0.055), size)
            r, g, b = (r + (BLUE[0] - r) * dot, g + (BLUE[1] - g) * dot, b + (BLUE[2] - b) * dot)
            row += bytes((round(r), round(g), round(b), round(alpha * 255)))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, rounded_square: bool) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(size, rounded_square), 9))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    # iOS rounds apple-touch-icon itself and renders transparency as black, so
    # that one is a full-bleed opaque square; the PWA icons keep rounded corners.
    for name, size, rounded in (("icon-512.png", 512, True), ("icon-192.png", 192, True), ("apple-touch-icon.png", 180, False)):
        (ICONS / name).write_bytes(png(size, rounded))
        print("wrote", name)
