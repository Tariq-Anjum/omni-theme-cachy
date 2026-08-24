"""Unit tests for core.theme_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import ColorError, ThemeLoadError
from core.theme_loader import discover_themes, find_theme, load_theme

from tests.conftest import FULL_PALETTE, write_theme


class TestLoadTheme:
    def test_loads_complete_theme(self, make_theme):
        theme_dir = make_theme("mytheme", mode="dark")
        theme = load_theme(theme_dir)

        assert theme.meta.name == "Test"
        assert theme.meta.id == "test"
        assert theme.meta.version == 1
        assert theme.meta.mode == "dark"
        assert theme.meta.is_dark
        assert theme.path == theme_dir
        assert len(theme.palette) == len(FULL_PALETTE)
        assert theme.color("accent") == FULL_PALETTE["accent"]

    def test_colors_normalized_to_lowercase(self, make_theme):
        theme_dir = make_theme(colors={"accent": "#4F9EEA", "muted": "#ABC"})
        theme = load_theme(theme_dir)
        assert theme.color("accent") == "#4f9eea"
        assert theme.color("muted") == "#aabbcc"  # documented #RGB expansion

    def test_wallpaper_resolution(self, make_theme):
        theme_dir = make_theme()
        (theme_dir / "wallpapers").mkdir()
        (theme_dir / "wallpapers" / "test.png").write_bytes(b"png")

        theme = load_theme(theme_dir)
        resolved = theme.resolve_wallpaper()
        assert resolved == theme_dir / "wallpapers" / "test.png"
        assert resolved.is_file()

    def test_embedded_colors_table_fallback(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "embedded",
            theme_toml=(
                "[theme]\n"
                'name = "E"\nid = "e"\nversion = 3\nmode = "light"\n\n'
                "[colors]\n"
                'accent = "#ff0000"\n'
            ),
        )
        # remove colors.toml to exercise the fallback
        (theme_dir / "colors.toml").unlink()

        theme = load_theme(theme_dir)
        assert theme.meta.mode == "light"
        assert theme.meta.is_light
        assert theme.palette.get("accent") == "#ff0000"

    def test_colors_toml_wins_over_embedded(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "both",
            colors={"accent": "#00ff00"},
            theme_toml=(
                "[theme]\nname = \"B\"\nid = \"b\"\nversion = 1\nmode = \"dark\"\n\n"
                "[colors]\naccent = \"#ff0000\"\n"
            ),
        )
        assert load_theme(theme_dir).color("accent") == "#00ff00"

    def test_missing_directory(self, tmp_path):
        with pytest.raises(ThemeLoadError):
            load_theme(tmp_path / "nope")

    def test_missing_theme_toml(self, tmp_path):
        theme_dir = write_theme(tmp_path / "x")
        (theme_dir / "theme.toml").unlink()
        with pytest.raises(ThemeLoadError, match="missing file"):
            load_theme(theme_dir)

    def test_missing_colors_everywhere(self, tmp_path):
        theme_dir = write_theme(tmp_path / "y")
        (theme_dir / "colors.toml").unlink()
        with pytest.raises(ThemeLoadError, match="no colors"):
            load_theme(theme_dir)

    def test_invalid_toml_syntax(self, make_theme):
        theme_dir = make_theme(theme_toml="[theme\nname = broken")
        with pytest.raises(ThemeLoadError, match="invalid TOML"):
            load_theme(theme_dir)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("version", 0), ("version", -2), ("version", "1"), ("version", True),
         ("mode", "blue"), ("mode", ""), ("name", "")],
    )
    def test_bad_metadata_rejected(self, tmp_path, field, value):
        meta = {
            "name": 'name = "T"',
            "id": 'id = "t"',
            "version": "version = 1",
            "mode": 'mode = "dark"',
        }
        rendered = repr(value)
        meta[field] = f"{field} = {rendered}"
        body = "[theme]\n" + "\n".join(meta.values()) + "\n"
        theme_dir = write_theme(tmp_path / "badmeta", theme_toml=body)
        with pytest.raises(ThemeLoadError):
            load_theme(theme_dir)

    def test_missing_metadata_field(self, tmp_path):
        body = '[theme]\nname = "T"\nid = "t"\nmode = "dark"\n'  # no version
        theme_dir = write_theme(tmp_path / "noversion", theme_toml=body)
        with pytest.raises(ThemeLoadError, match="version"):
            load_theme(theme_dir)

    def test_malformed_color_names_role(self, make_theme):
        theme_dir = make_theme(colors={"accent": "#zzz123"})
        with pytest.raises(ColorError, match="accent"):
            load_theme(theme_dir)

    def test_non_string_color_rejected(self, make_theme):
        theme_dir = make_theme(theme_toml=None)
        (theme_dir / "colors.toml").write_text('accent = 0x4f9eea\n')
        with pytest.raises((ColorError, ThemeLoadError)):
            load_theme(theme_dir)


class TestDiscoverAndFind:
    def test_discover_finds_only_valid_dirs_sorted(self, make_theme, tmp_path):
        make_theme("beta")
        make_theme("alpha")
        (tmp_path / "notatheme").mkdir()
        found = discover_themes(tmp_path)
        assert found == [tmp_path / "alpha", tmp_path / "beta"]

    def test_discover_empty_or_missing_root(self, tmp_path):
        assert discover_themes(tmp_path) == []
        assert discover_themes(tmp_path / "missing") == []

    def test_find_by_directory_name(self, make_theme):
        theme_dir = make_theme("solarized-ish")
        assert find_theme(theme_dir.parent, "solarized-ish") == theme_dir

    def test_find_by_id_and_name(self, make_theme, tmp_path):
        make_theme("dir-a")  # id=test name=Test
        assert find_theme(tmp_path, "test") == tmp_path / "dir-a"
        assert find_theme(tmp_path, "Test") == tmp_path / "dir-a"

    def test_find_explicit_path(self, make_theme):
        theme_dir = make_theme("explicit")
        assert find_theme(theme_dir.parent, theme_dir) == theme_dir

    def test_find_miss_raises(self, tmp_path):
        with pytest.raises(ThemeLoadError, match="no theme matching"):
            find_theme(tmp_path, "ghost")
