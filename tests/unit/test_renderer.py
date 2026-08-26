"""Unit tests for core.renderer (session 03)."""

from __future__ import annotations

import pytest

from core.errors import RenderError
from core.theme_loader import load_theme
from core.renderer import build_context, render_template_file, render_text


class TestPlainSubstitution:
    def test_palette_role(self, make_theme):
        theme = load_theme(make_theme())
        assert render_text("background={{ background }}", theme) == (
            f"background={theme.color('background')}"
        )

    def test_whitespace_tolerant(self, make_theme):
        theme = load_theme(make_theme())
        assert render_text("{{  accent  }}", theme) == theme.color("accent")

    def test_multiple_expressions_one_line(self, make_theme):
        theme = load_theme(make_theme())
        out = render_text("{{ accent }}/{{ background }}", theme)
        assert out == f"{theme.color('accent')}/{theme.color('background')}"

    def test_dotted_surface_key(self, make_theme):
        theme = load_theme(make_theme())
        out = render_text("{{ popups.background }}", theme)
        assert out == "#1e222b"

    def test_surface_number_value(self, make_theme):
        theme = load_theme(make_theme())
        assert render_text("w={{ popups.border-width }}", theme) == "w=2"

    def test_plain_name_beats_suffix_decomposition(self, tmp_path):
        """An explicit `x_rgb` role must win over `x` + `_rgb` filter."""
        from tests.conftest import write_theme

        theme = load_theme(write_theme(tmp_path / "t", colors={"accent_rgb": "#112233"}))
        assert render_text("{{ accent_rgb }}", theme) == "#112233"
        # ...while the suffix form still works for plain roles.
        assert render_text("{{ accent_strip }}", theme) == theme.color("accent")[1:]


class TestColorFilters:
    def test_strip(self, make_theme):
        theme = load_theme(make_theme())
        assert render_text("{{ accent_strip }}", theme) == theme.color("accent").lstrip("#")

    def test_rgb(self, make_theme):
        theme = load_theme(make_theme())
        r, g, b = (int(theme.color("accent")[i : i + 2], 16) for i in (1, 3, 5))
        assert render_text("{{ accent_rgb }}", theme) == f"{r}, {g}, {b}"

    def test_filters_work_on_surface_colors(self, make_theme):
        theme = load_theme(make_theme())
        assert render_text("{{ popups.background_strip }}", theme) == "1e222b"


class TestMixHelpers:
    @pytest.mark.parametrize(
        ("helper", "expect_hash"),
        [("mix", True), ("mix_strip", False), ("mix_rgb", False)],
    )
    def test_mix_ratio_forms_agree(self, make_theme, helper, expect_hash):
        theme = load_theme(make_theme())
        variants = [
            render_text(f"{{{{ {helper} accent background {t} }}}}", theme)
            for t in ("20%", "0.2", "20")
        ]
        assert variants[0] == variants[1] == variants[2]
        if expect_hash:
            assert variants[0].startswith("#")
        else:
            assert "#" not in variants[0]

    def test_mix_value_correct(self, make_theme):
        theme = load_theme(make_theme())
        out = render_text("{{ mix color0 color15 50% }}", theme)
        from core.color import mix

        assert out == mix(theme.color("color0"), theme.color("color15"), "50%")

    def test_mix_accepts_literal_hex_operands(self, make_theme):
        theme = load_theme(make_theme())
        from core.color import mix

        expected = mix("#000000", "#ffffff", 0.5)
        assert render_text("{{ mix #000000 #ffffff 0.5 }}", theme) == expected

    def test_mix_strip_has_no_hash(self, make_theme):
        out = render_text("{{ mix_strip accent background 10% }}", load_theme(make_theme()))
        assert "#" not in out and len(out) == 6

    def test_mix_rgb_decimal_channels(self, make_theme):
        from core.color import mix_rgb

        theme = load_theme(make_theme())
        out = render_text("{{ mix_rgb red blue 25 }}", theme)
        r, g, b = mix_rgb(theme.color("red"), theme.color("blue"), "25%")
        assert out == f"{r}, {g}, {b}"

    def test_bad_ratio_raises(self, make_theme):
        with pytest.raises(RenderError, match="bad ratio"):
            render_text("{{ mix accent background banana }}", load_theme(make_theme()))

    def test_out_of_range_ratio_raises(self, make_theme):
        with pytest.raises(RenderError, match="bad ratio"):
            render_text("{{ mix accent background 150% }}", load_theme(make_theme()))

    def test_wrong_arity_raises(self, make_theme):
        with pytest.raises(RenderError, match="exactly 3 arguments"):
            render_text("{{ mix accent background }}", load_theme(make_theme()))


class TestKdeGradient:
    def test_vertical_angle_default(self, tmp_path):
        from tests.conftest import surfaces_toml_text, write_theme

        theme = load_theme(write_theme(
            tmp_path / "t",
            surfaces=surfaces_toml_text(
                {"decor": {"fade": "rgba(33ccffff) rgba(00ff99ff)"}}
            ),
        ))
        out = render_text("{{ kde_gradient decor.fade }}", theme)
        assert out == (
            "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            "stop:0 rgba(51, 204, 255, 100%), stop:1 rgba(0, 255, 153, 100%))"
        )

    def test_45deg_direction_is_bottomleft_to_topright(self, make_theme):
        out = render_text("{{ kde_gradient controls.focus-border }}", make_theme())
        assert out.startswith("qlineargradient(x1:0, y1:1, x2:1, y2:0, ")

    def test_alpha_rendered_as_percentage(self, tmp_path):
        from tests.conftest import surfaces_toml_text, write_theme

        theme = load_theme(write_theme(
            tmp_path / "t",
            surfaces=surfaces_toml_text(
                {"decor": {"g": "rgba(33ccffee) rgba(00ff99ee)"}}
            ),
        ))
        out = render_text("{{ kde_gradient decor.g }}", theme)
        assert "rgba(51, 204, 255, 93%)" in out
        assert "rgba(0, 255, 153, 93%)" in out

    def test_unknown_reference_raises(self, make_theme):
        with pytest.raises(RenderError, match="unknown variable 'decor.nope'"):
            render_text("{{ kde_gradient decor.nope }}", load_theme(make_theme()))

    def test_non_gradient_value_raises(self, make_theme):
        # popups.background is a single color, not a multi-stop gradient
        with pytest.raises(RenderError, match="needs at least two stops"):
            render_text("{{ kde_gradient popups.background }}", make_theme())


class TestStrictErrors:
    def test_unknown_variable_names_offender_and_candidates(self, make_theme):
        with pytest.raises(RenderError, match="unknown variable 'acccent'") as info:
            render_text("{{ acccent }}", load_theme(make_theme()))
        assert "defined variables" in str(info.value)

    def test_error_reports_line_number(self, make_theme):
        text = "line one\nline two\n{{ missing_thing }}"
        with pytest.raises(RenderError, match="<text>:3:"):
            render_text(text, load_theme(make_theme()))

    def test_error_prefers_explicit_template_name(self, tmp_path, make_theme):
        tpl = tmp_path / "x.tpl"
        tpl.write_text("{{ nope }}")
        with pytest.raises(RenderError, match=str(tpl)):
            render_template_file(tpl, load_theme(make_theme()))

    def test_unclosed_expression_raises(self, make_theme):
        with pytest.raises(RenderError, match="unclosed"):
            render_text("hello {{ oops", load_theme(make_theme()))

    def test_empty_expression_raises(self, make_theme):
        with pytest.raises(RenderError, match="empty expression"):
            render_text("{{ }}", load_theme(make_theme()))

    def test_unknown_helper_raises(self, make_theme):
        with pytest.raises(RenderError, match="cannot evaluate"):
            render_text("{{ darken accent 20 }}", load_theme(make_theme()))

    def test_no_silent_empty_expansion(self, make_theme):
        """The whole point of strict mode: garbage in, exception out."""
        rendered = ""
        try:
            rendered = render_text("a={{ does_not_exist_at_all }}", load_theme(make_theme()))
        except RenderError:
            pass
        assert rendered == ""

    def test_unreadable_template_file_raises(self, tmp_path):
        with pytest.raises(RenderError, match="cannot read template"):
            render_template_file(tmp_path / "missing.tpl", {})


def test_build_context_shape(make_theme):
    ctx = build_context(load_theme(make_theme()))
    assert ctx["accent"].startswith("#")
    assert ctx["popups.background"] == "#1e222b"
    assert ctx["popups.border-width"] == 2
    assert "color7" in ctx and "bright_cyan" in ctx
