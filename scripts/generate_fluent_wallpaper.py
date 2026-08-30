#!/usr/bin/env python3
"""Generate the fluent-glass theme wallpaper (original work, stdlib only).

Deep navy base with electric-blue aurora ribbons, a magenta glow on the
left and cyan highlights — modeled on the fluent-glass reference look.

Usage: python scripts/generate_fluent_wallpaper.py [WIDTH HEIGHT OUT]
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

DEFAULT_OUT = Path("themes/fluent-glass/wallpapers/default.png")

WIDTH, HEIGHT = 1920, 1080

BASE_TOP = (0x05, 0x0D, 0x20)
BASE_BOTTOM = (0x0A, 0x1A, 0x33)

MAGENTA = (0xD6, 0x44, 0xC8)
PINK = (0xE8, 0x5C, 0xA0)
BLUE = (0x1E, 0x6E, 0xE0)
CYAN = (0x35, 0xC4, 0xFF)


def render(width: int, height: int) -> bytearray:
    rng_state = 12345

    def noise() -> float:
        nonlocal rng_state
        rng_state = (1103515245 * rng_state + 12345) % (1 << 31)
        return rng_state / float(1 << 31) - 0.5

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        ty = y / (height - 1)
        base = [
            round(a + (b - a) * ty) for a, b in zip(BASE_TOP, BASE_BOTTOM)
        ]
        row = bytearray()
        for x in range(width):
            tx = x / (width - 1)
            r, g, b = base

            # magenta glow anchored left-center, tilted
            gx, gy = 0.16 - 0.06 * ty, 0.55 + 0.08 * tx
            d2 = (tx - gx) ** 2 + (ty - gy) ** 2
            glow = math.exp(-d2 / 0.012)
            r = min(255, round(r + (MAGENTA[0] - r) * glow * 0.85))
            g = min(255, round(g + (MAGENTA[1] - g) * glow * 0.55))
            b = min(255, round(b + (MAGENTA[2] - b) * glow * 0.85))

            # pink core inside the magenta glow
            core = math.exp(-d2 / 0.003)
            r = min(255, round(r + (PINK[0] - r) * core * 0.8))
            g = min(255, round(g + (PINK[1] - g) * core * 0.6))
            b = min(255, round(b + (PINK[2] - b) * core * 0.8))

            # blue ribbons sweeping the right half
            for center, amp, tight, strength in (
                (0.62, 0.16, 0.004, 0.55),
                (0.80, 0.22, 0.006, 0.45),
                (0.95, 0.12, 0.003, 0.35),
            ):
                cy_abs = center + amp * math.sin(tx * 3.1 + center * 9.0)
                dist = abs(ty - cy_abs)
                band = math.exp(-dist * dist / tight) * strength
                if band > 0.01:
                    r = min(255, round(r + (BLUE[0] - r) * band))
                    g = min(255, round(g + (BLUE[1] - g) * band))
                    b = min(255, round(b + (BLUE[2] - b) * band))
                    # cyan edge highlight where the band is steepest
                    edge = max(0.0, band - 0.35) * 1.4
                    if edge > 0.01:
                        r = min(255, round(r + (CYAN[0] - r) * edge))
                        g = min(255, round(g + (CYAN[1] - g) * edge))
                        b = min(255, round(b + (CYAN[2] - b) * edge))

            # dither to avoid banding
            n = noise() * 2.5
            row += bytes(
                (
                    max(0, min(255, round(r + n))),
                    max(0, min(255, round(g + n))),
                    max(0, min(255, round(b + n))),
                )
            )
        raw.extend(row)
    return raw


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, raw: bytearray, width: int, height: int) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(png_chunk(b"IHDR", ihdr))
        fh.write(png_chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        fh.write(png_chunk(b"IEND", b""))
    print(f"wrote {path} ({width}x{height}, {path.stat().st_size // 1024} KiB)")


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) == 2 else DEFAULT_OUT
    write_png(out, render(WIDTH, HEIGHT), WIDTH, HEIGHT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
