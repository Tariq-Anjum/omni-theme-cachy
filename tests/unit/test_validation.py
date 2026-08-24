"""Unit tests for core.validation, including the shipped default theme."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import ThemeValidationError
from core.theme_loader import load_theme
from core.validation import (
    UI_CONTRAST_MIN,
    validate_theme,
    validate_theme_dir,
)

from tests.conftest import FULL_PALETTE, SURFACES_TOML, write_theme

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_THEME = PROJECT_ROOT / "themes" / "default"

class TestSurfacesRules:
    def test_shipped_default_surfaces_validate_clean(self):
        theme = load_theme(DEFAULT_THEME)
        assert "NO_SURFACES" not in {i.code for i in validate_theme(theme)}
        assert theme.surfaces.get("popups", "border-width") == 2

    def test_missing_surfaces_warns(self, tmp_path):
        theme_dir = write_theme(tmp_path / "nosurf", surfaces=None)
        issues = validate_theme_dir(theme_dir)
        assert {"NO_SURFACES"} <= codes_of(issues)
        assert all(i.code != "NO_SURFACES" or not i.is_error for i in issues)

    def test_unknown_surface_group_warns(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "extragroup",
            surfaces=SURFACES_TOML + '\n[lock]\nborder = "#ffffff"\n',
        )
        issues = validate_theme_dir(theme_dir)
        found = [i for i in issues if i.code == "UNKNOWN_SURFACE_GROUP"]
        assert len(found) == 1
        assert "[lock]" in found[0].message
        assert not found[0].is_error

    def test_bad_gradient_is_error_via_pure_model(self, make_theme):
        from core.theme_model import Surfaces, Theme, ThemeMeta
        surfaces = Surfaces(
            {"controls": {"focus-border": "rgba(33ccff) rgba(00ff99ee)"}}
        )
        theme = Theme(meta=ThemeMeta("T", "t", 1, "dark"), palette=dict(FULL_PALETTE), surfaces=surfaces)
        bad = [i for i in validate_theme(theme) if i.code == "SURFACE_BAD_VALUE"]
        assert len(bad) == 1
        assert "focus-border" in bad[0].message
        assert bad[0].is_error

    def test_bad_gradient_maps_to_surface_code_via_dir(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "badgrad",
            surfaces='[controls]\nfocus-border = "rgba(33ccff) rgba(00ff99ee)"\n',
        )
        assert "SURFACE_BAD_VALUE" in codes_of(validate_theme_dir(theme_dir))

    def test_bad_border_width_maps_to_surface_code_via_dir(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "badwidth",
            surfaces='[popups]\nborder-width = "1 2 3 4 5"\n',
        )
        issues = validate_theme_dir(theme_dir)
        assert any(
            i.code == "SURFACE_BAD_VALUE" and "border-width" in i.message
            for i in issues
        )

    def test_alpha_out_of_range_flagged(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "alpha",
            surfaces="[controls]\nfill-alpha = 2\n",
        )
        assert "SURFACE_BAD_VALUE" in codes_of(validate_theme_dir(theme_dir))

    def test_valid_surfaces_produce_no_issues(self, tmp_path):
        theme_dir = write_theme(tmp_path / "good")
        (theme_dir / "wallpapers").mkdir()
        (theme_dir / "wallpapers" / "test.png").write_bytes(b"x")
        assert validate_theme_dir(theme_dir) == []


def codes_of(issues):
    return {i.code for i in issues}


class TestShippedDefaultTheme:
    def test_default_theme_is_clean(self):
        """The flagship theme must load and produce zero errors AND zero warnings."""
        assert DEFAULT_THEME.is_dir(), "themes/default is missing from the repo"
        issues = validate_theme_dir(DEFAULT_THEME)
        assert issues == []

    def test_loaded_theme_pure_validation_agrees(self):
        issues = validate_theme(load_theme(DEFAULT_THEME))
        assert not any(i.is_error for i in issues)


class TestColorRules:
    def test_missing_required_color_is_error(self, make_theme):
        theme = load_theme(make_theme(omit={"color7", "accent_secondary"}))
        issues = validate_theme(theme)
        assert {"MISSING_COLOR"} <= codes_of(issues)
        missing_msgs = [i.message for i in issues if i.code == "MISSING_COLOR"]
        assert any("color7" in m for m in missing_msgs)
        assert any("accent_secondary" in m for m in missing_msgs)
        assert any(i.is_error for i in issues)

    def test_unknown_color_is_warning_only(self, make_theme):
        theme = load_theme(make_theme(colors={"cursor": "#ffffff"}))
        issues = validate_theme(theme)
        unknown = [i for i in issues if i.code == "UNKNOWN_COLOR"]
        assert len(unknown) == 1
        assert "cursor" in unknown[0].message
        assert not unknown[0].is_error

    def test_malformed_color_in_model(self):
        from core.theme_model import Palette, Theme, ThemeMeta
        palette = Palette(dict(FULL_PALETTE, red="#GGGGGG"))
        theme = Theme(meta=ThemeMeta("T", "t", 1, "dark"), palette=palette)
        issues = validate_theme(theme)
        assert "BAD_COLOR" in codes_of(issues)

    def test_non_normalized_color_flagged(self):
        from core.theme_model import Palette, Theme, ThemeMeta
        palette = Palette(dict(FULL_PALETTE, accent="#4F9EEA"))
        theme = Theme(meta=ThemeMeta("T", "t", 1, "dark"), palette=palette)
        assert "NON_NORMALIZED_COLOR" in codes_of(validate_theme(theme))


class TestWallpaperRules:
    def test_missing_wallpaper_file_is_error(self, make_theme):
        theme_dir = make_theme()  # wallpapers/test.png declared but never created
        issues = validate_theme_dir(theme_dir)
        assert any(i.is_error and i.code == "WALLPAPER_MISSING" for i in issues)

    def test_present_wallpaper_passes(self, make_theme):
        theme_dir = make_theme()
        (theme_dir / "wallpapers").mkdir()
        (theme_dir / "wallpapers" / "test.png").write_bytes(b"x")
        assert validate_theme_dir(theme_dir) == []

    def test_wallpaper_outside_theme_dir_warns(self, tmp_path):
        outside = tmp_path / "elsewhere.png"
        outside.write_bytes(b"x")
        theme_dir = write_theme(tmp_path / "t")
        (theme_dir / "theme.toml").write_text(
            '[theme]\nname="T"\nid="t"\nversion=1\nmode="dark"\n\n'
            '[wallpaper]\ndefault="../elsewhere.png"\n'
        )
        issues = validate_theme_dir(theme_dir)
        assert {"WALLPAPER_OUTSIDE_THEME"} <= codes_of(issues)

    def test_no_wallpaper_declared_warns(self, tmp_path):
        theme_dir = write_theme(
            tmp_path / "nowall",
            theme_toml='[theme]\nname="T"\nid="t"\nversion=1\nmode="dark"\n',
        )
        found = codes_of(validate_theme_dir(theme_dir))
        assert "NO_WALLPAPER" in found
        assert "WALLPAPER_MISSING" not in found


class TestContrastRules:
    def _theme_with(self, **overrides):
        from core.theme_model import Palette, Theme, ThemeMeta
        meta = ThemeMeta("T", "t", 1, "dark")
        return Theme(meta=meta, palette=Palette(dict(FULL_PALETTE, **overrides)))

    def test_identical_foreground_background_triggers_warnings(self):
        theme = self._theme_with(foreground="#14161c")  # == background
        contrast_issues = [i for i in validate_theme(theme) if i.code == "CONTRAST_LOW"]
        pairs = {i.message.split(":")[0] for i in contrast_issues}
        assert "foreground vs background" in pairs
        assert all(i.severity == "warning" for i in contrast_issues)

    def test_low_contrast_accent_uses_ui_threshold(self):
        # ratio(#3c3f44-ish gray-blue on background) sits between 3.0 and 4.5
        theme = self._theme_with(accent="#3d4a58")
        issues = [i for i in validate_theme(theme) if i.code == "CONTRAST_LOW"]
        assert any("accent vs background" in i.message for i in issues)
        assert str(UI_CONTRAST_MIN) in issues[0].message

    def test_healthy_palette_has_no_contrast_warnings(self):
        theme = self._theme_with()
        assert [i for i in validate_theme(theme) if i.code == "CONTRAST_LOW"] == []


class TestValidateThemeDir:
    def test_broken_toml_becomes_issue_not_exception(self, make_theme):
        theme_dir = make_theme(theme_toml="[theme\nname = oops")
        issues = validate_theme_dir(theme_dir)
        assert "LOAD_FAILED" in codes_of(issues)
        assert any(i.is_error for i in issues)

    def test_bad_color_becomes_bad_color_code(self, make_theme):
        theme_dir = make_theme(colors={"accent": "nothex"})
        issues = validate_theme_dir(theme_dir)
        assert "BAD_COLOR" in codes_of(issues)

    def test_missing_directory_reported(self, tmp_path):
        issues = validate_theme_dir(tmp_path / "ghost")
        assert [i.code for i in issues] == ["THEME_DIR_MISSING"]

    def test_unknown_section_warns(self, tmp_path):
        body = (
            '[theme]\nname="T"\nid="t"\nversion=1\nmode="dark"\n\n'
            '[wallpaper]\ndefault="wallpapers/test.png"\n\n'
            "[fonts]\nterminal = \"mono\"\n"
        )
        theme_dir = write_theme(tmp_path / "extra", theme_toml=body)
        (theme_dir / "wallpapers").mkdir()
        (theme_dir / "wallpapers" / "test.png").write_bytes(b"x")
        issues = validate_theme_dir(theme_dir)
        found = codes_of(issues)
        assert "UNKNOWN_SECTION" in found
        assert any("[fonts]" in i.message for i in issues)

    def test_strict_mode_raises_on_errors(self, make_theme):
        theme_dir = make_theme(omit={"color0"})
        with pytest.raises(ThemeValidationError) as excinfo:
            validate_theme_dir(theme_dir, strict=True)
        assert excinfo.value.issues  # carries full detail

    def test_strict_mode_passes_clean_theme(self, tmp_path):
        theme_dir = write_theme(tmp_path / "clean")
        (theme_dir / "wallpapers").mkdir()
        (theme_dir / "wallpapers" / "test.png").write_bytes(b"x")
        assert validate_theme_dir(theme_dir, strict=True) == []


class TestCli:
    def test_validate_default_via_cli_ok(self, capsys):
        from core.cli import main
        exit_code = main(["theme", "validate", "default", "--root", str(PROJECT_ROOT / "themes")])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_validate_json_output(self, make_theme, tmp_path, capsys):
        from core.cli import main
        broken = make_theme(colors={"accent": "nothex"})
        code = main(["theme", "validate", str(broken), "--json"])
        assert code == 1
        import json
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert any(i["code"] == "BAD_COLOR" for i in payload["issues"])

    def test_validate_unknown_reference_exit_2(self, tmp_path, capsys):
        from core.cli import main
        code = main(["theme", "validate", "ghost", "--root", str(tmp_path)])
        assert code == 2
        err = capsys.readouterr().err
        assert "error:" in err

    def test_strict_fails_on_warnings(self, tmp_path):
        from core.cli import main
        # warnings-only theme: no [wallpaper] section → NO_WALLPAPER warning
        theme_dir = write_theme(
            tmp_path / "warny",
            theme_toml='[theme]\nname="T"\nid="t"\nversion=1\nmode="dark"\n',
        )
        assert main(["theme", "validate", str(theme_dir)]) == 0
        assert main(["theme", "validate", str(theme_dir), "--strict"]) == 1
