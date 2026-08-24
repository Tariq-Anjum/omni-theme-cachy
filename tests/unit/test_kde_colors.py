"""Unit tests for the Omni palette → KDE Color Scheme mapping model.

Hermetic: no KDE binaries, no filesystem side effects outside tmp_path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.renderer import render_template_file, resolve_template  # noqa: E402

from adapters.kde import colors as kc  # noqa: E402
from tests.conftest import FULL_PALETTE, SURFACES_TOML, write_theme  # noqa: E402

# --------------------------------------------------------------------------- #
# Mapping table shape


class TestMappingTables:
    def test_every_mapped_role_exists_in_palette_contract(self):
        from core.theme_model import REQUIRED_COLORS

        missing = set(kc.MAPPED_ROLE_KEYS) - set(REQUIRED_COLORS)
        assert not missing, f"mapping references undefined roles: {missing}"

    def test_all_sets_covered_for_fleet_keys(self):
        for role in ("background", "accent", "error"):
            targets = dict(kc.KDE_COLOR_MAP[role])
            assert set(targets) == set(kc.COLOR_SETS), role
        # text roles intentionally skip Colors:Selection (bright text there)
        for role in ("foreground", "muted"):
            targets = dict(kc.KDE_COLOR_MAP[role])
            assert set(targets) == set(kc.COLOR_SETS) - {"Colors:Selection"}, role

    def test_selection_normal_text_is_special_cased(self):
        targets = dict(kc.KDE_COLOR_MAP["foreground"])
        assert ("Colors:Selection", "ForegroundNormal") not in {
            (s, k) for s, k in kc.KDE_COLOR_MAP["foreground"]
        }

    def test_no_invented_sections_or_keys(self):
        """Every emitted key must come from the verified upstream vocabulary."""
        allowed = set(kc.SET_KEYS)
        for role, targets in kc.KDE_COLOR_MAP.items():
            for section, key in targets:
                assert section in kc.COLOR_SETS
                assert key in allowed, f"{role}: {key}"
        for targets in kc.POPUPS_MAP.values():
            for section, key in targets:
                assert section in kc.COLOR_SETS
                assert key in allowed

    def test_unsupported_surfaces_declare_reasons(self):
        assert "controls.normal-border" in kc.SURFACE_UNSUPPORTED
        assert kc.SURFACE_UNSUPPORTED["controls.normal-border"]
        assert "border" in kc.SURFACE_UNSUPPORTED["controls.normal-border"].lower()


# --------------------------------------------------------------------------- #
# Value model


class TestExpectedSchemeValues:
    def test_basic_role_mapping(self):
        values = kc.expected_scheme_values(FULL_PALETTE)
        window_bg = values[("Colors:Window", "BackgroundNormal")]
        assert (window_bg.role, window_bg.value) == ("background", FULL_PALETTE["background"])

    def test_status_hues_map_to_semantic_foregrounds(self):
        values = kc.expected_scheme_values(FULL_PALETTE)
        assert values[("Colors:View", "ForegroundPositive")].value == FULL_PALETTE["success"]
        assert values[("Colors:View", "ForegroundNegative")].value == FULL_PALETTE["error"]
        assert values[("Colors:View", "ForegroundNeutral")].value == FULL_PALETTE["warning"]
        assert values[("Colors:View", "ForegroundLink")].value == FULL_PALETTE["info"]

    def test_accent_drives_decorations_everywhere(self):
        values = kc.expected_scheme_values(FULL_PALETTE)
        for section in kc.COLOR_SETS:
            for key in ("DecorationFocus", "DecorationHover"):
                assert values[(section, key)].value == FULL_PALETTE["accent"]

    def test_selection_uses_dedicated_roles(self):
        values = kc.expected_scheme_values(FULL_PALETTE)
        assert values[("Colors:Selection", "BackgroundNormal")].role == "selection"
        assert (
            values[("Colors:Selection", "ForegroundNormal")].value
            == FULL_PALETTE["bright_foreground"]
        )

    def test_popups_background_direct_when_authored(self):
        surfaces = {"popups": {"background": "#1e222b"}}
        values = kc.expected_scheme_values(FULL_PALETTE, surfaces)
        tooltip = values[("Colors:Tooltip", "BackgroundNormal")]
        complementary = values[("Colors:Complementary", "BackgroundNormal")]
        assert tooltip.value == "#1e222b"
        assert complementary.value == "#1e222b"
        assert tooltip.role == "popups.background"

    def test_popups_background_derived_when_missing(self):
        values = kc.expected_scheme_values(FULL_PALETTE, None)
        tooltip = values[("Colors:Tooltip", "BackgroundNormal")]
        assert tooltip.role == "<derived:popups.background>"
        assert tooltip.value == kc.elevated_background(FULL_PALETTE)
        # derived elevation must differ from base background
        assert tooltip.value != FULL_PALETTE["background"]

    def test_wm_section_uses_titlebar_roles(self):
        values = kc.expected_scheme_values(FULL_PALETTE)
        assert values[("WM", "activeBackground")].value == FULL_PALETTE["lighter_background"]
        assert values[("WM", "inactiveForeground")].value == FULL_PALETTE["dark_foreground"]


# --------------------------------------------------------------------------- #
# Surface mapping report


class TestSurfaceReport:
    def test_full_surfaces_report_modes(self):
        surfaces = {
            "popups": {"background": "#1e222b"},
            "controls": {
                "normal-border": "#3a4150",
                "focus-border": "rgba(4f9eeaee) rgba(8f6cafee) 45deg",
            },
        }
        rows = {r.surface: r for r in kc.surface_mapping_report(surfaces)}
        assert rows["popups.background"].mode == "direct"
        assert rows["controls.focus-border"].mode == "semantic"
        assert rows["controls.normal-border"].mode == "unsupported"
        assert rows["controls.normal-border"].reason

    def test_missing_surfaces_report_derived(self):
        rows = {r.surface: r for r in kc.surface_mapping_report(None)}
        assert rows["popups.background"].mode == "derived"
        assert "derived" in rows["popups.background"].reason.lower()


# --------------------------------------------------------------------------- #
# Parsing / verification / serialization


class TestParseAndVerify:
    def test_parse_scheme_text_round_trip(self):
        text = "[Colors:Window]\nBackgroundNormal = 20, 22, 28\n"
        parsed = kc.parse_scheme_text(text)
        assert parsed[("Colors:Window", "BackgroundNormal")] == "20, 22, 28"

    def test_parse_ignores_comments_and_blank_lines(self):
        text = "# hi\n\n[General]\nColorScheme=X\n"
        assert kc.parse_scheme_text(text)[("General", "ColorScheme")] == "X"

    def test_normalize_triplet_variants(self):
        assert kc.normalize_triplet("20, 22, 28") == "20,22,28"
        assert kc.normalize_triplet("20,22,28") == "20,22,28"

    def test_verify_accepts_faithful_text(self):
        values = {k: v.value for k, v in kc.expected_scheme_values(FULL_PALETTE).items()}
        text = kc.scheme_text(
            name="OmniTheme", display_name="Omni Theme", values=values
        )
        assert kc.verify_scheme_text(text, FULL_PALETTE) == []

    def test_verify_detects_tampering(self):
        values = {k: v.value for k, v in kc.expected_scheme_values(FULL_PALETTE).items()}
        text = kc.scheme_text(name="OmniTheme", display_name="Omni Theme", values=values)
        tampered = text.replace(
            kc.rgb_triplet(FULL_PALETTE["accent"]),
            "1,2,3",
        )
        problems = kc.verify_scheme_text(tampered, FULL_PALETTE)
        assert problems and all("DecorationFocus" in p or "DecorationHover" in p
                                or "ForegroundActive" in p for p in problems)

    def test_verify_detects_missing_key(self):
        text = "[Colors:Window]\nBackgroundNormal=1,2,3\n[General]\nColorScheme=X\n"
        problems = kc.verify_scheme_text(text, FULL_PALETTE)
        assert any("missing" in p for p in problems)

    def test_rgb_triplet_format(self):
        assert kc.rgb_triplet("#4f9eea") == "79,158,234"


# --------------------------------------------------------------------------- #
# Template parity (both tiers)


class TestTemplateParity:
    def test_builtin_template_matches_model_without_surfaces(self, tmp_path):
        # strip surfaces so resolution falls back to the built-in tier
        theme_dir = write_theme(tmp_path / "bare", surfaces=None)
        resolved = resolve_template(
            "kde/OmniTheme.colors.tpl",
            theme_dir=theme_dir,
            builtin_root=PROJECT_ROOT / "templates",
        )
        assert resolved.origin == "builtin"
        text = render_template_file(resolved.path, theme_dir)
        from core.theme_loader import load_theme

        palette = dict(load_theme(theme_dir).palette.colors)
        assert kc.verify_scheme_text(text, palette, None) == []

    def test_theme_tier_override_maps_popups(self, tmp_path):
        """The shipped default theme's override maps its authored popup bg."""
        theme_dir = PROJECT_ROOT / "themes" / "default"
        resolved = resolve_template(
            "kde/OmniTheme.colors.tpl",
            theme_dir=theme_dir,
            builtin_root=PROJECT_ROOT / "templates",
        )
        assert resolved.origin == "theme"

        from core.theme_loader import load_theme

        theme = load_theme(theme_dir)
        text = render_template_file(resolved.path, theme)
        palette = dict(theme.palette.colors)
        surfaces = dict(theme.surfaces.items())
        assert kc.verify_scheme_text(text, palette, surfaces) == []
        authored = surfaces["popups"]["background"]
        parsed = kc.parse_scheme_text(text)
        assert (
            kc.normalize_triplet(parsed[("Colors:Tooltip", "BackgroundNormal")])
            == kc.rgb_triplet(authored)
        )

    def test_both_templates_agree_outside_popup_sets(self):
        """Builtin and theme-tier templates share structure and values
        everywhere except the popup-driven Tooltip/Complementary fills."""
        from core.theme_loader import load_theme

        theme_dir = PROJECT_ROOT / "themes" / "default"
        theme = load_theme(theme_dir)

        def render(tier_root, themes_dir):
            resolved = resolve_template(
                "kde/OmniTheme.colors.tpl",
                theme_dir=themes_dir,
                builtin_root=PROJECT_ROOT / "templates",
            )
            assert resolved.origin == tier_root
            return render_template_file(resolved.path, theme)

        theme_text = render("theme", theme_dir)
        builtin_text = render("builtin", Path("/nonexistent-theme-dir"))

        def key_map(text: str) -> dict:
            parsed = kc.parse_scheme_text(text)
            popup_keys = {
                ("Colors:Tooltip", "BackgroundNormal"),
                ("Colors:Tooltip", "BackgroundAlternate"),
                ("Colors:Complementary", "BackgroundNormal"),
                ("Colors:Complementary", "BackgroundAlternate"),
            }
            return {
                k: kc.normalize_triplet(v)
                for k, v in parsed.items()
                if k not in popup_keys
            }

        assert key_map(builtin_text) == key_map(theme_text)

    def test_shipped_default_theme_renders_through_builtin_root(self):
        """The repo's own default theme renders its override cleanly."""
        theme_dir = PROJECT_ROOT / "themes" / "default"
        resolved = resolve_template(
            "kde/OmniTheme.colors.tpl",
            theme_dir=theme_dir,
            builtin_root=PROJECT_ROOT / "templates",
        )
        assert resolved.origin == "theme"  # ships its own override
        from core.theme_loader import load_theme

        theme = load_theme(theme_dir)
        text = render_template_file(resolved.path, theme)
        assert kc.verify_scheme_text(
            text, dict(theme.palette.colors), dict(theme.surfaces.items())
        ) == []


# --------------------------------------------------------------------------- #
# Serialization


class TestSchemeText:
    def test_serialization_shape(self):
        values = {k: v.value for k, v in kc.expected_scheme_values(FULL_PALETTE).items()}
        text = kc.scheme_text(name="OmniTheme", display_name="Omni Theme", values=values)
        assert text.startswith("[ColorEffects:Disabled]")
        assert "[Colors:Header]" in text
        assert "[General]" in text
        assert "ColorScheme=OmniTheme" in text
        assert "Name=Omni Theme" in text
        assert "contrast=4" in text
        assert "[WM]" in text

    def test_effects_blocks_are_upstream_verbatim(self):
        values = {k: v.value for k, v in kc.expected_scheme_values(FULL_PALETTE).items()}
        text = kc.scheme_text(name="X", display_name="X", values=values)
        assert "ContrastAmount=0.65" in text  # BreezeDark's disabled contrast
        assert "Enable=false" in text  # inactive effects disabled upstream

    def test_targets_registry_declares_scheme_target(self):
        import tomllib

        registry = tomllib.loads((PROJECT_ROOT / "templates/targets.toml").read_text())
        entries = registry["template"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["adapter"] == "kde-colorscheme"
        assert entry["source"]["path"] == "kde/OmniTheme.colors.tpl"
        assert entry["target"]["path"].endswith("color-schemes/OmniTheme.colors")

    def test_safe_id_validation(self):
        from adapters.kde.config import safe_scheme_id
        from core.errors import AdapterError

        assert safe_scheme_id("OmniTheme") == "OmniTheme"
        with pytest.raises(AdapterError):
            safe_scheme_id("../evil")
        with pytest.raises(AdapterError):
            safe_scheme_id("")
