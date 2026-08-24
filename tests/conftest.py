"""Shared fixtures for omni-theme-cachy unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# A complete, known-good palette mirroring themes/default. Inlined on
# purpose so these tests stay hermetic w.r.t. shipped assets.
_SEMANTIC = {
    "background": "#14161c",
    "darker_background": "#0e1015",
    "dark_background": "#101218",
    "lighter_background": "#1a1d25",
    "foreground": "#d6dae2",
    "bright_foreground": "#f5f7fa",
    "light_foreground": "#eef0f4",
    "dark_foreground": "#8a919d",
    "muted": "#7d8593",
    "accent": "#4f9eea",
    "accent_secondary": "#8f6caf",
    "selection": "#294664",
    "success": "#82a55b",
    "warning": "#d9a05b",
    "error": "#d9564f",
    "info": "#5b8ec4",
    "red": "#d9564f",
    "green": "#82a55b",
    "yellow": "#d9a05b",
    "blue": "#5b8ec4",
    "magenta": "#a064ca",
    "cyan": "#54a8ae",
    "bright_red": "#e8878f",
    "bright_green": "#9cc98f",
    "bright_yellow": "#e6be86",
    "bright_blue": "#82abdc",
    "bright_magenta": "#bb8ade",
    "bright_cyan": "#74c4ca",
}

_ANSI = [
    "#2a2e39", "#d9564f", "#82a55b", "#d9a05b",
    "#5b8ec4", "#a064ca", "#54a8ae", "#c5cbd6",
    "#565d6d", "#e8878f", "#9cc98f", "#e6be86",
    "#82abdc", "#bb8ade", "#74c4ca", "#eceff4",
]

FULL_PALETTE: dict[str, str] = {
    **_SEMANTIC,
    **{f"color{i}": c for i, c in enumerate(_ANSI)},
}

THEME_TOML = """\
[theme]
name = "Test"
id = "test"
version = 1
mode = "{mode}"

[wallpaper]
default = "wallpapers/test.png"
"""


def write_theme(
    directory: Path,
    *,
    mode: str = "dark",
    colors: dict[str, str] | None = None,
    omit: frozenset[str] | set[str] = frozenset(),
    theme_toml: str | None = None,
) -> Path:
    """Materialize a theme directory under *directory* and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "theme.toml").write_text(
        theme_toml if theme_toml is not None else THEME_TOML.format(mode=mode)
    )
    palette = {k: v for k, v in FULL_PALETTE.items() if k not in omit}
    palette.update(colors or {})
    lines = "\n".join(f'{role} = "{value}"' for role, value in palette.items())
    (directory / "colors.toml").write_text(lines + "\n")
    return directory


@pytest.fixture
def palette_dict() -> dict[str, str]:
    return dict(FULL_PALETTE)


@pytest.fixture
def make_theme(tmp_path):
    """Factory building complete (or deliberately broken) theme dirs."""
    counter = iter(range(10_000))

    def make(name: str | None = None, **kwargs) -> Path:
        label = name or f"theme-{next(counter)}"
        return write_theme(tmp_path / label, **kwargs)

    return make
