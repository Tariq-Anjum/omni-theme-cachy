"""Unit tests for user-overlay deep merging (session 03, Omarchy pattern)."""

from __future__ import annotations

import pytest

from core.errors import ColorError, SurfaceValueError
from core.theme_loader import load_theme, load_theme_with_overlay


def write_overlay(directory, colors=None, surfaces=None):
    directory.mkdir(parents=True, exist_ok=True)
    if colors is not None:
        lines = "\n".join(f'{k} = "{v}"' for k, v in colors.items())
        (directory / "colors.toml").write_text(lines + "\n")
    if surfaces is not None:
        chunks = []
        for group, entries in surfaces.items():
            body = "\n".join(f"{k} = {v!r}" if not isinstance(v, str) else f'{k} = "{v}"'
                             for k, v in entries.items())
            chunks.append(f"[{group}]\n{body}")
        (directory / "surfaces.toml").write_text("\n\n".join(chunks) + "\n")
    return directory


class TestOverlayBasics:
    def test_missing_overlay_dir_returns_base_theme(self, make_theme):
        theme_dir = make_theme()
        base = load_theme(theme_dir)
        merged, report = load_theme_with_overlay(
            theme_dir, theme_dir.parent / "does-not-exist"
        )
        assert dict(merged.palette.colors) == dict(base.palette.colors)
        assert report.applied is False
        assert report.ownership == "base"

    def test_none_overlay_dir_is_not_an_error(self, make_theme):
        theme, report = load_theme_with_overlay(make_theme(), None)
        assert report.ownership == "base"
        assert theme.color("accent") == "#4f9eea"

    def test_single_key_override(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(theme_dir.parent / "overlay", colors={"accent": "#ff0000"})
        merged, report = load_theme_with_overlay(theme_dir, overlay)
        assert merged.color("accent") == "#ff0000"
        # untouched keys survive
        assert merged.color("background") == "#14161c"
        assert report.applied and report.ownership == "user-overlay"
        assert report.colors == frozenset({"accent"})

    def test_additive_keys_allowed(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(theme_dir.parent / "overlay", colors={"brand_extra": "#00ff00"})
        merged, report = load_theme_with_overlay(theme_dir, overlay)
        assert merged.color("brand_extra") == "#00ff00"
        assert "brand_extra" in report.colors

    def test_empty_overlay_files_count_as_noop(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(theme_dir.parent / "overlay", colors={})
        _, report = load_theme_with_overlay(theme_dir, overlay)
        assert report.applied is False
        assert report.ownership == "base"


class TestDeepMergeSurfaces:
    def test_group_and_key_level_merge(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(
            theme_dir.parent / "overlay",
            surfaces={"popups": {"border-width": 4, "extra": "#123456"}},
        )
        merged, report = load_theme_with_overlay(theme_dir, overlay)
        # overridden
        assert merged.surfaces.get("popups", "border-width") == 4
        # added
        assert merged.surfaces.get("popups", "extra") == "#123456"
        # sibling keys from base survive
        assert merged.surfaces.get("popups", "border") == "#4f9eea"
        # untouched group survives
        assert merged.surfaces.get("controls", "focus-border") == (
            "rgba(4f9eeaee) rgba(8f6cafee) 45deg"
        )
        assert ("popups", "border-width") in report.surfaces

    def test_new_group_added(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(
            theme_dir.parent / "overlay", surfaces={"panels": {"opacity": 0}}
        )
        merged, _ = load_theme_with_overlay(theme_dir, overlay)
        assert merged.surfaces.group("panels") == {"opacity": 0}


class TestOverlayValidation:
    def test_bad_color_in_overlay_raises(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(theme_dir.parent / "overlay", colors={"accent": "not-a-color"})
        with pytest.raises(ColorError, match="accent"):
            load_theme_with_overlay(theme_dir, overlay)

    def test_bad_surface_value_in_overlay_raises(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(
            theme_dir.parent / "overlay",
            surfaces={"popups": {"border-width": -3}},
        )
        with pytest.raises(SurfaceValueError):
            load_theme_with_overlay(theme_dir, overlay)

    def test_base_theme_file_never_mutated(self, make_theme):
        theme_dir = make_theme()
        overlay = write_overlay(theme_dir.parent / "overlay", colors={"accent": "#ff0000"})
        before = (theme_dir / "colors.toml").read_text()
        merged, _ = load_theme_with_overlay(theme_dir, overlay)
        assert (theme_dir / "colors.toml").read_text() == before
        assert merged.color("accent") == "#ff0000"


def test_report_records_source_paths(make_theme):
    theme_dir = make_theme()
    overlay = write_overlay(
        theme_dir.parent / "overlay",
        colors={"accent": "#ff0000"},
        surfaces={"popups": {"border-width": 6}},
    )
    _, report = load_theme_with_overlay(theme_dir, overlay)
    assert report.colors_path == overlay / "colors.toml"
    assert report.surfaces_path == overlay / "surfaces.toml"
