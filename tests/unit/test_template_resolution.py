"""Unit tests for template resolution precedence (session 03)."""

from __future__ import annotations

import pytest

from core.errors import TemplateNotFoundError
from core.renderer import (
    TEMPLATE_ORIGIN_BUILTIN,
    TEMPLATE_ORIGIN_THEME,
    TEMPLATE_ORIGIN_USER,
    resolve_template,
)


@pytest.fixture
def roots(tmp_path):
    """Three resolution tiers with the same logical template name."""
    user = tmp_path / "user-templates"
    theme = tmp_path / "theme" / "templates"
    builtin = tmp_path / "builtin"
    for root in (user, theme, builtin):
        (root / "kde").mkdir(parents=True)
    return user, theme, builtin


def _write(root, name: str, marker: str) -> None:
    (root / name).write_text(marker)


class TestPrecedence:
    def test_user_wins_over_theme_and_builtin(self, roots):
        user, theme, builtin = roots
        _write(user, "kde/x.tpl", "USER")
        _write(theme, "kde/x.tpl", "THEME")
        _write(builtin, "kde/x.tpl", "BUILTIN")

        resolved = resolve_template("kde/x.tpl", theme_dir=roots_theme_dir(roots),
                                    user_templates_dir=user, builtin_root=builtin)
        assert resolved.origin == TEMPLATE_ORIGIN_USER
        assert resolved.path == user / "kde/x.tpl"

    def test_theme_wins_over_builtin(self, roots):
        user, theme, builtin = roots
        _write(theme, "kde/x.tpl", "THEME")
        _write(builtin, "kde/x.tpl", "BUILTIN")

        resolved = resolve_template("kde/x.tpl", theme_dir=roots_theme_dir(roots),
                                    user_templates_dir=user, builtin_root=builtin)
        assert resolved.origin == TEMPLATE_ORIGIN_THEME

    def test_builtin_is_final_fallback(self, roots):
        _, _, builtin = roots
        _write(builtin, "kde/x.tpl", "BUILTIN")

        resolved = resolve_template("kde/x.tpl", theme_dir=None,
                                    user_templates_dir=None, builtin_root=builtin)
        assert resolved.origin == TEMPLATE_ORIGIN_BUILTIN


class TestFailure:
    def test_not_found_lists_all_searched_paths(self, roots):
        user, theme, builtin = roots
        with pytest.raises(TemplateNotFoundError) as info:
            resolve_template("kde/absent.tpl", theme_dir=roots_theme_dir(roots),
                             user_templates_dir=user, builtin_root=builtin)
        message = str(info.value)
        assert str(user / "kde/absent.tpl") in message
        assert str(theme / "kde/absent.tpl") in message
        assert str(builtin / "kde/absent.tpl") in message

    def test_absolute_name_rejected(self, tmp_path):
        with pytest.raises(TemplateNotFoundError, match="relative"):
            resolve_template("/etc/passwd", builtin_root=tmp_path)

    def test_empty_name_rejected(self):
        with pytest.raises(TemplateNotFoundError):
            resolve_template("", builtin_root=".")


# -- helpers ----------------------------------------------------------------


def roots_theme_dir(roots):
    """The theme *directory* (its templates/ subdir is tier two)."""
    return roots[1].parent
