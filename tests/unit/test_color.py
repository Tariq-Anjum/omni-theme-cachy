"""Unit tests for core.color."""

from __future__ import annotations

import pytest

from core.color import (
    BorderWidth,
    Gradient,
    GradientStop,
    classify_surface_value,
    contrast_ratio,
    hex_to_rgb,
    hex_to_rgb_string,
    mix,
    mix_rgb,
    normalize_ratio,
    parse_border_width,
    parse_gradient,
    relative_luminance,
    rgb_to_hex,
    strip_hex,
    validate_surface_value,
)
from core.errors import ColorError, SurfaceValueError


class TestStripHex:
    def test_canonical_form(self):
        assert strip_hex("#1a2b3c") == "1a2b3c"

    def test_uppercase_normalized(self):
        assert strip_hex("#ABCDEF") == "abcdef"

    @pytest.mark.parametrize(
        ("short", "long"),
        [("#abc", "aabbcc"), ("#FFF", "ffffff"), ("#0f0", "00ff00")],
    )
    def test_rgb_shorthand_expands_nibbles(self, short, long):
        assert strip_hex(short) == long

    @pytest.mark.parametrize("value", ["", "#", "#ab", "#abcd", "#abcde7f", "#12g45z", "1a2b3c", "#aabbc"])
    def test_malformed_rejected(self, value):
        with pytest.raises(ColorError):
            strip_hex(value)

    def test_non_string_rejected(self):
        with pytest.raises(ColorError):
            strip_hex(0x112233)


class TestConversions:
    def test_hex_to_rgb(self):
        assert hex_to_rgb("#4f9eea") == (79, 158, 234)

    def test_rgb_to_hex(self):
        assert rgb_to_hex(79, 158, 234) == "#4f9eea"

    def test_round_trip(self):
        for value in ("#000000", "#ffffff", "#14161c", "#a064ca"):
            assert rgb_to_hex(*hex_to_rgb(value)) == value.lower()

    @pytest.mark.parametrize(("r", "g", "b", "expected"), [(255.4, 0, 0, "#ff0000"), (254.6, 0, 0, "#ff0000"), (10.6, 20, 30, "#0b141e")])
    def test_rgb_to_hex_rounds_floats(self, r, g, b, expected):
        assert rgb_to_hex(r, g, b) == expected

    def test_rgb_to_hex_clamps_float_slop(self):
        assert rgb_to_hex(-0.2, 255.2, 128) == "#00ff80"

    @pytest.mark.parametrize("channels", [(-2, 0, 0), (257, 0, 0), (999, 0, 0), (True, 0, 0), ("x", 0, 0)])
    def test_rgb_to_hex_rejects_bad_channels(self, channels):
        with pytest.raises(ColorError):
            rgb_to_hex(*channels)

    def test_hex_to_rgb_string_default(self):
        assert hex_to_rgb_string("#14161c") == "20, 22, 28"

    def test_hex_to_rgb_string_custom_separator(self):
        assert hex_to_rgb_string("#14161c", separator=",") == "20,22,28"


class TestNormalizeRatio:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(0.5, 0.5), (1, 1.0), (0, 0.0), (50, 0.5), (100, 1.0), ("50%", 0.5), ("100%", 1.0), ("15%", 0.15), ("0.35", 0.35)],
    )
    def test_accepted_forms(self, raw, expected):
        assert normalize_ratio(raw) == pytest.approx(expected)

    def test_percent_with_spaces(self):
        assert normalize_ratio(" 35 % ") == pytest.approx(0.35)

    @pytest.mark.parametrize("raw", [150, -5, "-10%", "abc", None, [], True])
    def test_out_of_range_or_garbage_rejected(self, raw):
        with pytest.raises(ColorError):
            normalize_ratio(raw)


class TestMix:
    def test_endpoints(self):
        assert mix("#000000", "#ffffff", 0) == "#000000"
        assert mix("#000000", "#ffffff", 1.0) == "#ffffff"
        assert mix("#000000", "#ffffff", "100%") == "#ffffff"

    def test_midpoint(self):
        assert mix("#000000", "#ffffff", 0.5) == "#808080"

    def test_quarter_blend_matches_formula(self):
        # round(0.75*20 + 0.25*79), etc. for #14161c blended toward #4f9eea
        expected = rgb_to_hex(
            round(0.75 * 0x14 + 0.25 * 0x4F),
            round(0.75 * 0x16 + 0.25 * 0x9E),
            round(0.75 * 0x1C + 0.25 * 0xEA),
        )
        assert mix("#14161c", "#4f9eea", 0.25) == expected

    def test_percent_and_fraction_agree(self):
        a, b = "#294664", "#54a8ae"
        assert mix(a, b, 35) == mix(a, b, "35%")
        assert mix_rgb(a, b, 35) == mix_rgb(a, b, 0.35)

    def test_mix_rgb_channels(self):
        assert mix_rgb("#000000", "#102030", 0.5) == (8, 16, 24)

    def test_result_always_valid_hex(self):
        result = mix("#123456", "#fedcba", 0.37)
        assert strip_hex(result) == result[1:]


class TestLuminanceAndContrast:
    def test_luminance_bounds(self):
        assert relative_luminance("#000000") == 0.0
        assert relative_luminance("#ffffff") == pytest.approx(1.0)

    def test_luminance_gray_known_value(self):
        # WCAG reference: mid-gray sRGB ≈ 0.2159
        assert relative_luminance("#777777") == pytest.approx(0.1841, abs=1e-3)

    def test_contrast_black_white_is_21(self):
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)

    def test_contrast_identical_is_1(self):
        assert contrast_ratio("#4f9eea", "#4f9eea") == pytest.approx(1.0)

    def test_contrast_symmetric(self):
        assert contrast_ratio("#14161c", "#d6dae2") == contrast_ratio("#d6dae2", "#14161c")

    def test_default_theme_core_pair_meets_aa(self):
        ratio = contrast_ratio("#d6dae2", "#14161c")
        assert ratio >= 4.5


class TestParseGradient:
    def test_omarchy_canonical_form(self):
        g = parse_gradient("rgba(33ccffee) rgba(00ff99ee) 45deg")
        assert isinstance(g, Gradient)
        assert g.angle == 45.0
        assert g.stops == (
            GradientStop(color="#33ccff", alpha=238 / 255),
            GradientStop(color="#00ff99", alpha=238 / 255),
        )
        assert g.stops[0].alpha_byte == 238
        assert g.stops[0].alpha_hex == "ee"

    def test_alpha_ff_is_opaque_and_00_transparent(self):
        g = parse_gradient("rgba(112233ff) rgba(44556600) 90deg")
        assert g.stops[0].alpha == 1.0
        assert g.stops[1].alpha == 0.0

    def test_angle_optional(self):
        g = parse_gradient("#14161c #4f9eea")
        assert g.angle is None
        assert [s.color for s in g.stops] == ["#14161c", "#4f9eea"]

    @pytest.mark.parametrize(("raw", "expected"), [("45deg", 45.0), ("45", 45.0), ("-30.5deg", -30.5), ("0DEG", 0.0)])
    def test_angle_forms(self, raw, expected):
        text = f"#111111 #222222 {raw}"
        assert parse_gradient(text).angle == expected

    def test_uppercase_rgba_wrapper_accepted(self):
        g = parse_gradient("RGBA(33CCFFEE) RGBA(00FF99EE) 45deg")
        assert g.stops[0].color == "#33ccff"

    def test_mixed_stop_styles(self):
        g = parse_gradient("rgba(33ccffee) #4f9eea 45deg")
        assert [s.color for s in g.stops] == ["#33ccff", "#4f9eea"]
        assert [s.alpha for s in g.stops] == [pytest.approx(238 / 255), 1.0]

    def test_three_stops(self):
        g = parse_gradient("#000000 #808080 #ffffff 120deg")
        assert len(g.stops) == 3
        assert g.angle == 120.0

    def test_round_trip_via_str(self):
        text = "rgba(33ccffee) rgba(00ff99ee) 45deg"
        assert str(parse_gradient(text)) == text

    def test_str_omits_unset_angle(self):
        assert str(parse_gradient("#112233 #445566")) == "rgba(112233ff) rgba(445566ff)"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "#14161c",                      # single stop
            "rgba(33ccffee)",               # single translucent token
            "rgba(33ccff) #4f9eea 45deg",   # 6 hex digits inside parens
            "rgba(33ccffgg) #4f9eea",       # non-hex digits
            "#zzzzzz #4f9eea",              # malformed plain stop
            "red blue",                     # named colors unsupported
            "#111111 #222222 45deg extra",  # junk after angle
            "#111111 #222222 fortyfive",    # bad angle token
            42,
            None,
        ],
    )
    def test_malformed_rejected(self, raw):
        with pytest.raises(SurfaceValueError):
            parse_gradient(raw)


class TestParseBorderWidth:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (2, BorderWidth(2, 2, 2, 2)),
            ("2", BorderWidth(2, 2, 2, 2)),
            ("2 4", BorderWidth(2, 4, 2, 4)),      # T/B R/L
            ("2 4 6", BorderWidth(2, 4, 6, 4)),    # T R/L B
            ("2 4 6 8", BorderWidth(2, 4, 6, 8)),  # T R B L
            (0, BorderWidth(0, 0, 0, 0)),
            ("0 0 0 0", BorderWidth(0, 0, 0, 0)),
        ],
    )
    def test_css_shorthand_expansion(self, raw, expected):
        assert parse_border_width(raw) == expected

    def test_namedtuple_accessors(self):
        bw = parse_border_width("1 2 3 4")
        assert (bw.top, bw.right, bw.bottom, bw.left) == (1, 2, 3, 4)

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "1 2 3 4 5", "-1", "-1 2", "x", "1 x", "1.5", "1.5 2", True, None, 2.5, ["2"]],
    )
    def test_malformed_rejected(self, raw):
        with pytest.raises(SurfaceValueError):
            parse_border_width(raw)


class TestSurfaceValues:
    @pytest.mark.parametrize(
        ("key", "value", "kind"),
        [
            ("background", "#1a1b26", "color"),
            ("focus-border", "rgba(33ccffee) rgba(00ff99ee) 45deg", "gradient"),
            ("border-width", 2, "border-width"),
            ("border-width", "2 4 6 8", "border-width"),
            ("scrim-alpha", 0.5, "alpha"),
            ("fill-alpha", 0, "alpha"),
            ("padding", 12, "number"),
        ],
    )
    def test_classification(self, key, value, kind):
        assert classify_surface_value(key, value) == kind

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("background", "nothex"),                       # bare word, no '#' or spaces
            ("background", "#zzzzzz"),                      # bad hex
            ("border-width", "2 x"),
            ("border-width", -3),
            ("border-width", []),
            ("scrim-alpha", 1.5),
            ("scrim-alpha", -0.1),
            ("scrim-alpha", "0.5"),
            ("padding", -4),
            ("padding", 4.2),
            ("anything", True),
            ("background", ""),
            ("background", None),
        ],
    )
    def test_rejections(self, key, value):
        with pytest.raises(SurfaceValueError):
            classify_surface_value(key, value)

    def test_validate_surface_value_is_quiet_on_success(self):
        validate_surface_value("focus-border", "#7aa2f7")  # must not raise
        validate_surface_value("border-width", "2 4")
