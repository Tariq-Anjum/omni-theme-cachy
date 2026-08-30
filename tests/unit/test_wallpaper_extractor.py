"""Tests for the stdlib-only wallpaper color extractor."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from core.errors import ThemeError
from core.wallpaper_extractor import (
    PALETTE_ROLES,
    WallpaperColorExtractor,
    WallpaperExtractionError,
)


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(kind + body) - len(kind))
        + kind
        + body
        + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    )


def write_png(
    path: Path,
    pixels: list[tuple[int, int, int]],
    width: int,
    height: int,
) -> Path:
    """Minimal 8-bit RGB, non-interlaced PNG writer (stdlib only)."""
    raw = b"".join(
        b"\x00" + bytes(v for px in pixels[row * width:(row + 1) * width] for v in px)
        for row in range(height)
    )
    data = b"\x89PNG\r\n\x1a\n"
    data += _png_chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    )
    data += _png_chunk(b"IDAT", zlib.compress(raw))
    data += _png_chunk(b"IEND", b"")
    path.write_bytes(data)
    return path


@pytest.fixture
def two_color_png(tmp_path: Path) -> Path:
    """Half dark navy, half light sand — two obvious clusters."""
    pixels = [(20, 24, 38)] * 400 + [(226, 214, 182)] * 400
    return write_png(tmp_path / "two.png", pixels, 40, 20)


@pytest.fixture
def monochrome_png(tmp_path: Path) -> Path:
    return write_png(
        tmp_path / "flat.png", [(19, 22, 30)] * 1600, 40, 40
    )


def test_roles_complete_and_valid(two_color_png: Path):
    palette = WallpaperColorExtractor().extract(two_color_png)
    assert set(palette) == set(PALETTE_ROLES)
    for value in palette.values():
        assert len(value) == 7 and value.startswith("#")
        int(value[1:], 16)


def test_dark_image_yields_dark_theme(two_color_png: Path):
    palette = WallpaperColorExtractor().extract(two_color_png)
    assert palette["background"] == "#141826"  # the navy cluster
    assert palette["foreground"] == "#e2d6b6"  # the sand cluster


def test_deterministic(two_color_png: Path):
    extractor = WallpaperColorExtractor()
    assert extractor.extract(two_color_png) == extractor.extract(two_color_png)


def test_stdlib_decoder_matches_pillow(two_color_png: Path, monkeypatch):
    """The pure-Python PNG path must byte-match the Pillow path."""
    import core.wallpaper_extractor as module

    palette_pillow = WallpaperColorExtractor().extract(two_color_png)
    monkeypatch.setattr(module, "_decode_via_pillow", lambda p: None)
    palette_stdlib = WallpaperColorExtractor().extract(two_color_png)
    assert palette_stdlib == palette_pillow


def test_monochrome_gets_readable_foreground_and_accent(monochrome_png: Path):
    palette = WallpaperColorExtractor().extract(monochrome_png)
    bg, fg = palette["background"], palette["foreground"]
    lum = lambda h: (0.2126 * int(h[1:3], 16) + 0.7152 * int(h[3:5], 16)
                     + 0.0722 * int(h[5:7], 16)) / 255
    assert lum(fg) - lum(bg) > 0.3          # readable pair
    assert lum(palette["accent"]) > 0.2     # accent is visible, not near-black


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(WallpaperExtractionError):
        WallpaperColorExtractor().extract(tmp_path / "nope.png")


def test_non_image_raises_without_pillow(tmp_path: Path, monkeypatch):
    import core.wallpaper_extractor as module

    bogus = tmp_path / "bogus.png"
    bogus.write_bytes(b"not an image at all")
    monkeypatch.setattr(module, "_decode_via_pillow", lambda p: None)
    with pytest.raises(WallpaperExtractionError):
        WallpaperColorExtractor().extract(bogus)


def test_corrupt_png_raises(tmp_path: Path, monkeypatch):
    import core.wallpaper_extractor as module

    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"\x89PNG\r\n\x1a\ngarbage")
    monkeypatch.setattr(module, "_decode_via_pillow", lambda p: None)
    with pytest.raises(WallpaperExtractionError):
        WallpaperColorExtractor().extract(corrupt)


def test_invalid_n_colors_rejected():
    with pytest.raises(ValueError):
        WallpaperColorExtractor(n_colors=1)


def test_extraction_error_is_theme_error():
    assert issubclass(WallpaperExtractionError, ThemeError)
