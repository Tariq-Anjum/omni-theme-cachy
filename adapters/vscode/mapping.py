"""Omni semantic roles → documented VS Code workbench color tokens.

Every key in :data:`SEMANTIC_TO_VSCODE` is a real, stable token from the
official ``workbench.colorCustomizations`` theme-color reference —
nothing is invented. The terminal ANSI ramp maps onto
``terminal.ansi*`` (16 tokens), and widget/popup surfaces prefer an
explicit ``popups.background`` surface role when the theme provides one.

Keys absent from a given theme's palette are simply not emitted; a
partial theme produces partial customizations rather than errors.
"""

from __future__ import annotations

from core.theme_model import Theme

__all__ = [
    "COLOR_CUSTOMIZATIONS_KEY",
    "SEMANTIC_TO_VSCODE",
    "ANSI_TO_VSCODE",
    "MANAGED_KEYS",
    "vscode_color_customizations",
]

#: The single top-level settings.json property this adapter owns.
COLOR_CUSTOMIZATIONS_KEY = "workbench.colorCustomizations"

#: Ordered mapping: VS Code token ← Omni palette role.
SEMANTIC_TO_VSCODE: tuple[tuple[str, str], ...] = (
    # editor base
    ("editor.background", "background"),
    ("editor.foreground", "foreground"),
    ("editor.selectionBackground", "selection"),
    ("editorLineNumber.foreground", "muted"),
    ("editorCursor.foreground", "bright_foreground"),
    # focus / active controls
    ("focusBorder", "accent"),
    # widgets & popups: explicit popup surface first, elevated bg fallback
    ("editorWidget.background", "@popup_or_lighter"),
    ("editorSuggestWidget.background", "@popup_or_lighter"),
    ("editorHoverWidget.background", "@popup_or_lighter"),
    # chrome surfaces
    ("sideBar.background", "dark_background"),
    ("panel.background", "darker_background"),
    ("titleBar.activeBackground", "dark_background"),
    # terminal base
    ("terminal.background", "dark_background"),
    ("terminal.foreground", "foreground"),
)

#: ``terminal.ansi<Token>`` (color0..7) and ``terminal.ansiBright<Token>``
#: (color8..15) ← ramp index.
ANSI_NAMES: tuple[str, ...] = (
    "Black", "Red", "Green", "Yellow",
    "Blue", "Magenta", "Cyan", "White",
)
ANSI_TO_VSCODE: tuple[tuple[str, str], ...] = tuple(
    [(f"terminal.ansi{ANSI_NAMES[i]}", f"color{i}") for i in range(8)]
    + [(f"terminal.ansiBright{ANSI_NAMES[i - 8]}", f"color{i}") for i in range(8, 16)]
)

#: Every settings key this adapter may write inside colorCustomizations.
MANAGED_KEYS: frozenset[str] = frozenset(
    key for key, _ in (*SEMANTIC_TO_VSCODE, *ANSI_TO_VSCODE)
)


def vscode_color_customizations(theme: Theme) -> dict[str, str]:
    """Compute the full colorCustomizations object for *theme*.

    Values are the theme's own normalized colors; roles the theme does
    not define are skipped silently. ``@popup_or_lighter`` resolves to
    the ``popups.background`` surface (hex only) or falls back to the
    ``lighter_background`` role.
    """
    palette = dict(theme.palette.colors)
    popup_surface = theme.surfaces.get("popups", "background")
    if isinstance(popup_surface, str) and popup_surface.startswith("#"):
        resolved_popup = popup_surface
    else:
        resolved_popup = None

    result: dict[str, str] = {}
    for token, source in SEMANTIC_TO_VSCODE:
        if source == "@popup_or_lighter":
            value = resolved_popup if resolved_popup else palette.get("lighter_background")
        else:
            value = palette.get(source)
        if value:
            result[token] = value.lower()
    for token, role in ANSI_TO_VSCODE:
        value = palette.get(role)
        if value:
            result[token] = value.lower()
    return result
