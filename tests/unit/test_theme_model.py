"""Unit tests for core.theme_model."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import ColorError, ThemeError
from core.theme_model import (
    ANSI_ROLES,
    KNOWN_SURFACE_GROUPS,
    REQUIRED_COLORS,
    REQUIRED_METADATA_FIELDS,
    SEMANTIC_ROLES,
    SURFACES_FILE,
    VALID_MODES,
    Palette,
    Surfaces,
    Theme,
    ThemeMeta,
    WallpaperConfig,
)


class TestConstants:
    def test_metadata_fields_complete(self):
        assert set(REQUIRED_METADATA_FIELDS) == {"name", "id", "version", "mode"}

    def test_modes(self):
        assert set(VALID_MODES) == {"dark", "light"}

    def test_ansi_ramp_is_color0_to_15(self):
        assert ANSI_ROLES == tuple(f"color{i}" for i in range(16))

    def test_semantic_roles_include_spec_minimum(self):
        expected = {
            "accent", "accent_secondary", "selection", "muted",
            "background", "dark_background", "darker_background",
            "lighter_background",
            "foreground", "dark_foreground", "light_foreground",
            "bright_foreground",
            "success", "warning", "error", "info",
            "red", "green", "yellow", "blue", "magenta", "cyan",
            "bright_red", "bright_green", "bright_yellow", "bright_blue",
            "bright_magenta", "bright_cyan",
        }
        assert expected <= set(SEMANTIC_ROLES)

    def test_required_colors_are_semantic_plus_ansi_without_duplicates(self):
        assert REQUIRED_COLORS == SEMANTIC_ROLES + ANSI_ROLES
        assert len(set(REQUIRED_COLORS)) == len(REQUIRED_COLORS)

    def test_surface_constants(self):
        assert KNOWN_SURFACE_GROUPS == (
            "popups", "controls", "panel", "kwin", "tooltips",
        )
        assert SURFACES_FILE == "surfaces.toml"


class TestThemeMeta:
    def test_polarity_flags(self):
        dark = ThemeMeta(name="N", id="n", version=1, mode="dark")
        light = ThemeMeta(name="L", id="l", version=2, mode="light")
        assert dark.is_dark and not dark.is_light
        assert light.is_light and not light.is_dark


class TestPalette:
    def test_get_returns_default_for_unknown(self):
        palette = Palette({"accent": "#4f9eea"})
        assert palette.get("accent") == "#4f9eea"
        assert palette.get("nope") is None
        assert palette.get("nope", "#000000") == "#000000"

    def test_color_raises_helpful_error(self):
        palette = Palette({"accent": "#4f9eea"})
        with pytest.raises(ColorError) as excinfo:
            palette.color("background")
        assert "background" in str(excinfo.value)
        assert "accent" in str(excinfo.value)  # lists known roles

    def test_require_collects_all_or_nothing(self):
        palette = Palette({"a": "#111111", "b": "#222222"})
        assert palette.require("a", "b") == {"a": "#111111", "b": "#222222"}
        with pytest.raises(ColorError) as excinfo:
            palette.require("a", "missing")
        assert "missing" in str(excinfo.value)

    def test_container_protocol(self):
        palette = Palette({"accent": "#4f9eea"})
        assert "accent" in palette
        assert "color0" not in palette
        assert list(palette) == ["accent"]
        assert len(palette) == 1
        assert dict(palette.items()) == {"accent": "#4f9eea"}


class TestWallpaperConfig:
    def test_empty_by_default(self):
        config = WallpaperConfig()
        assert config.default is None
        assert config.resolve(Path("/themes/x")) is None

    def test_relative_resolves_against_theme_dir(self):
        config = WallpaperConfig(default="wallpapers/w.png")
        assert config.resolve(Path("/themes/x")) == Path("/themes/x/wallpapers/w.png")

    def test_absolute_passthrough(self):
        config = WallpaperConfig(default="/usr/share/w.png")
        assert config.resolve(Path("/themes/x")) == Path("/usr/share/w.png")


class TestSurfaces:
    def test_empty_by_default(self):
        surfaces = Surfaces()
        assert len(surfaces) == 0
        assert surfaces.group("popups") == {}
        assert surfaces.get("popups", "border") is None
        assert "popups" not in surfaces

    def test_group_and_get(self):
        surfaces = Surfaces(
            {"popups": {"border": "#7aa2f7", "border-width": 2}}
        )
        assert surfaces.group("popups") == {"border": "#7aa2f7", "border-width": 2}
        assert surfaces.get("popups", "border-width") == 2
        assert surfaces.get("controls", "normal-border") is None
        assert surfaces.get("controls", "normal-border", "#ffffff") == "#ffffff"
        assert "popups" in surfaces
        assert dict(surfaces.items()) == surfaces.groups

    def test_values_preserved_as_authored(self):
        raw = {"popups": {"focus-border": "rgba(33ccffee) rgba(00ff99ee) 45deg"}}
        assert Surfaces(raw).get("popups", "focus-border") == raw["popups"]["focus-border"]


class TestTheme:
    def _meta(self, mode="dark"):
        return ThemeMeta(name="T", id="t", version=1, mode=mode)

    def test_dict_palette_convenience(self):
        theme = Theme(meta=self._meta(), palette={"accent": "#4f9eea"})
        assert isinstance(theme.palette, Palette)
        assert theme.color("accent") == "#4f9eea"
        assert theme.mode == "dark"

    def test_dict_surfaces_convenience(self):
        theme = Theme(meta=self._meta(), surfaces={"popups": {"border-width": 3}})
        assert isinstance(theme.surfaces, Surfaces)
        assert theme.surfaces.get("popups", "border-width") == 3

    def test_surfaces_default_empty(self):
        assert len(Theme(meta=self._meta()).surfaces) == 0

    def test_resolve_wallpaper_requires_path(self):
        theme = Theme(meta=self._meta(), wallpaper=WallpaperConfig("w.png"))
        with pytest.raises(ThemeError):
            theme.resolve_wallpaper()

    def test_resolve_wallpaper_with_path(self, tmp_path):
        theme = Theme(meta=self._meta(), wallpaper=WallpaperConfig("wallpapers/w.png"), path=tmp_path)
        assert theme.resolve_wallpaper() == tmp_path / "wallpapers" / "w.png"

    def test_frozen_model(self):
        from dataclasses import FrozenInstanceError
        theme = Theme(meta=self._meta())
        with pytest.raises(FrozenInstanceError):
            theme.meta = self._meta(mode="light")

    def test_missing_role_via_color_raises(self):
        theme = Theme(meta=self._meta())
        with pytest.raises(ColorError):
            theme.color("anything")
