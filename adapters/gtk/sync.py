"""KDE → GTK color propagation: verification of kde-gtk-config output.

When a KDE Color Scheme is applied, ``kdeglobals`` receives the scheme's
values and ``kde-gtk-config`` (the ``gtkconfig`` KDED module) rewrites
``~/.config/gtk-{3,4}.0/colors.css`` with matching ``@define-color``
entries. This module verifies that propagation actually happened —
it is the gtk adapter's *own* responsibility, independent of how
kdeglobals got its values (that is the kde adapter's verified part).

The pair table below was confirmed against a live Plasma 6.7 machine:
each ``(section, key)`` in kdeglobals equals the CSS color stored under
the paired ``@define-color`` name (modulo ``rgb()`` vs hex spelling).
Only confirmed pairs are used — nothing is guessed.
"""

from __future__ import annotations

import re
import time

from core.color import rgb_to_hex
from core import kde_config

from adapters.gtk.detection import GtkEnvironment

__all__ = [
    "SYNC_PAIRS",
    "PROPAGATION_WAIT_S",
    "PROPAGATION_POLL_S",
    "parse_kdeglobals",
    "parse_colors_css",
    "verify_sync",
    "await_sync",
]

#: kdeglobals ``(section, key)`` → colors.css ``@define-color`` name.
SYNC_PAIRS: tuple[tuple[tuple[str, str], str], ...] = (
    (("Colors:Window", "BackgroundNormal"), "theme_bg_color_breeze"),
    (("Colors:View", "BackgroundNormal"), "theme_base_color_breeze"),
    (("Colors:Window", "ForegroundNormal"), "theme_fg_color_breeze"),
    (("Colors:View", "ForegroundNormal"), "theme_text_color_breeze"),
    (("Colors:Selection", "BackgroundNormal"), "theme_selected_bg_color_breeze"),
    (("Colors:Selection", "ForegroundNormal"), "theme_selected_fg_color_breeze"),
)

_TRIPLET_RE = re.compile(r"^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$")
_DEFINE_RE = re.compile(
    r"@define-color\s+([A-Za-z0-9_]+)\s+" r"(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\s*;"
)


def parse_kdeglobals(text: str) -> dict[tuple[str, str], str]:
    """Parse KConfig INI into ``((section, key), value)`` map."""
    return kde_config.parse_ini(text)


def parse_colors_css(text: str) -> dict[str, str]:
    """Parse ``@define-color name value;`` entries into lowercase hex."""
    out: dict[str, str] = {}
    for match in _DEFINE_RE.finditer(text):
        name, raw_value = match.group(1), match.group(2)
        out[name] = _to_hex(raw_value)
    return out


def _to_hex(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if value.startswith("#"):
        return value[:7]
    match = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", value)
    if not match:
        return value
    try:
        channels = tuple(int(float(c)) for c in match.groups())
    except ValueError:
        return value
    return rgb_to_hex(*channels)


def verify_sync(
    kdeglobals_text: str,
    colors_css_text: str,
) -> list[str]:
    """Human-readable mismatches between kdeglobals and colors.css.

    Pairs missing from either side are reported as mismatches too: the
    caller decides whether absence means "sync not yet run" (warning)
    or a broken propagation (error) based on file existence.
    """
    globals_map = parse_kdeglobals(kdeglobals_text)
    css_map = parse_colors_css(colors_css_text)
    problems: list[str] = []
    for (section, key), css_name in SYNC_PAIRS:
        expected_raw = globals_map.get((section, key))
        actual = css_map.get(css_name)
        if expected_raw is None:
            problems.append(f"kdeglobals [{section}] {key} missing; cannot check {css_name}")
            continue
        if actual is None:
            problems.append(f"colors.css lacks @define-color {css_name}")
            continue
        triplet = _TRIPLET_RE.match(expected_raw)
        if not triplet:
            problems.append(
                f"kdeglobals [{section}] {key}={expected_raw!r} is not an RGB triplet"
            )
            continue
        expected = rgb_to_hex(*map(int, triplet.groups()))
        if actual != expected:
            problems.append(
                f"sync drift: {css_name} is {actual}, "
                f"kdeglobals [{section}] {key} says {expected}"
            )
    return problems


def environment_sync_inputs(env: GtkEnvironment) -> tuple[str | None, str | None]:
    """Read (kdeglobals text, gtk-3 colors.css text) for :func:`verify_sync`."""
    kdeglobals = env.config_home / "kdeglobals"
    css = env.colors_css("gtk-3.0")
    kg_text = None
    css_text = None
    try:
        kg_text = kdeglobals.read_text(encoding="utf-8")
    except OSError:
        pass
    if css is not None:
        try:
            css_text = css.read_text(encoding="utf-8")
        except OSError:
            pass
    return kg_text, css_text


#: kde-gtk-config rewrites colors.css *asynchronously* after kdeglobals
#: changes (observed ~0.2s behind on live Plasma 6.7). Verification that
#: runs immediately after a scheme application must allow the daemon
#: this window before declaring drift, otherwise a healthy activation
#: races the propagator and fails.
PROPAGATION_WAIT_S = 2.0
PROPAGATION_POLL_S = 0.1


def await_sync(
    env: GtkEnvironment,
    *,
    budget: float = PROPAGATION_WAIT_S,
    sleep=time.sleep,
) -> list[str]:
    """Re-check propagation until it settles or *budget* expires.

    Returns the final problem list (empty = verified). Purely
    read-only: it re-reads kdeglobals and colors.css, never writes.
    """
    deadline = time.monotonic() + budget
    kg_text, css_text = environment_sync_inputs(env)
    problems = verify_sync(kg_text or "", css_text or "")
    while problems and time.monotonic() < deadline:
        sleep(PROPAGATION_POLL_S)
        kg_text, css_text = environment_sync_inputs(env)
        problems = verify_sync(kg_text or "", css_text or "")
    return problems
