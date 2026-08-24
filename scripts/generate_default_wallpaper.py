#!/usr/bin/env python3
"""Generate the default theme wallpaper without any external assets.

Writes a subtle vertical gradient PNG (stdlib only: struct + zlib), so the
shipped artwork is original and license-clean by construction.

Usage: python scripts/generate_default_wallpaper.py [WIDTH HEIGHT OUT]
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

DEFAULT_OUT = Path("themes/default/wallpapers/default.png")

TOP = (0x10, 0x12, 0x18)      # darker_background-ish, top of frame
BOTTOM = (0x1E, 0x22, 0x2C)   # lighter_background-ish, bottom of frame


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_gradient_png(path: Path, width: int = 2560, height: int = 1440) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None) per scanline
        t = y / max(1, height - 1)
        row = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
        raw.extend(row * width)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(png_chunk(b"IHDR", ihdr))
        fh.write(png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        fh.write(png_chunk(b"IEND", b""))
    print(f"wrote {path} ({width}x{height}, {path.stat().st_size // 1024} KiB)")


def main(argv: list[str]) -> int:
    args = argv[1:]
    out = Path(args[0]) if len(args) == 1 else DEFAULT_OUT
    if len(args) == 3:
        write_gradient_png(Path(args[2]), int(args[0]), int(args[1]))
    else:
        write_gradient_png(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
