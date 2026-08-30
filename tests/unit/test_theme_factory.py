"""Tests for core.theme_factory (theme directory generation)."""

from __future__ import annotations

import pytest

from tests.conftest import FULL_PALETTE
from core.errors import ThemeError
from core.theme_factory import create_theme_dir, slugify
from core.theme_loader import load_theme
from core.validation import validate_theme


def test_slugify():
    assert slugify("Sunset Beach!") == "sunset-beach"
    assert slugify("  A  B  ") == "a-b"
    assert slugify("Ünïcode") == "n-code"  # non-ascii stripped
    with pytest.raises(ThemeError):
        slugify("///")


def test_create_and_load(tmp_path):
    theme_dir = create_theme_dir(
        tmp_path, name="Sunset", colors=dict(FULL_PALETTE), mode="dark"
    )
    theme = load_theme(theme_dir)
    assert theme.meta.id == "sunset"
    assert theme.meta.mode == "dark"
    assert theme.palette.color("background") == FULL_PALETTE["background"]
    assert theme.wallpaper.default is None
    assert not [i for i in validate_theme(theme) if i.is_error]


def test_create_with_wallpaper(tmp_path):
    wallpaper = tmp_path / "wall.png"
    wallpaper.write_bytes(b"\x89PNG\r\n\x1a\nstub")
    theme_dir = create_theme_dir(
        tmp_path, name="Sunset", colors=dict(FULL_PALETTE),
        wallpaper=wallpaper,
    )
    theme = load_theme(theme_dir)
    assert theme.resolve_wallpaper() == theme_dir / "wallpapers" / "wall.png"
    assert (theme_dir / "wallpapers" / "wall.png").read_bytes().startswith(b"\x89PNG")


def test_refuses_overwrite_without_force(tmp_path):
    create_theme_dir(tmp_path, name="Sunset", colors=dict(FULL_PALETTE))
    with pytest.raises(ThemeError, match="already exists"):
        create_theme_dir(tmp_path, name="Sunset", colors=dict(FULL_PALETTE))
    # force=True replaces in place.
    create_theme_dir(tmp_path, name="Sunset", colors=dict(FULL_PALETTE), force=True)


def test_rejects_incomplete_palette(tmp_path):
    with pytest.raises(ThemeError, match="missing roles"):
        create_theme_dir(tmp_path, name="Broken", colors={"background": "#000000"})


def test_rejects_invalid_mode(tmp_path):
    with pytest.raises(ThemeError, match="mode"):
        create_theme_dir(tmp_path, name="Sunset", colors=dict(FULL_PALETTE), mode="sepia")


def test_missing_wallpaper_raises(tmp_path):
    with pytest.raises(ThemeError, match="not found"):
        create_theme_dir(
            tmp_path, name="Sunset", colors=dict(FULL_PALETTE),
            wallpaper=tmp_path / "ghost.png",
        )
