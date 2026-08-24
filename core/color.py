"""Color engine for omni-theme-cachy.

Pure stdlib color math on ``#RRGGBB`` hex strings.

Accepted syntax
---------------
* ``#RRGGBB`` — the canonical form (case-insensitive; output is lowercase).
* ``#RGB``    — accepted as a convenience and *normalized by nibble
  expansion* (``#abc`` → ``#aabbcc``), matching CSS shorthand semantics.
  Every function here normalizes before use; nothing downstream ever sees
  the short form.

Anything else raises :class:`core.errors.ColorError`.

Mixing
------
:meth:`mix`/:meth:`mix_rgb` blend two colors with ``t`` = share of the
second color: ``t=0`` → first color, ``t=1`` → second color (CSS/GLSL
convention). For template convenience :meth:`normalize_ratio` accepts:

* floats in ``[0.0, 1.0]``  → used directly as a fraction
* ints/floats in ``(1.0, 100]`` → interpreted as a percentage (``50`` → 0.5)
* strings like ``"15%"`` or ``"35%"`` → parsed as a percentage

Luminance/contrast follow WCAG 2.x definitions.
"""

from __future__ import annotations

import re

from core.errors import ColorError

__all__ = [
    "strip_hex",
    "hex_to_rgb",
    "rgb_to_hex",
    "hex_to_rgb_string",
    "mix",
    "mix_rgb",
    "normalize_ratio",
    "relative_luminance",
    "contrast_ratio",
]

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_RGB_STRING_DEFAULT_SEP = ", "


def strip_hex(value: str) -> str:
    """Return the hex digits of *value*, lowercased, without ``#``.

    Normalizes ``#RGB`` to six digits. Raises ColorError when malformed.
    """
    if not isinstance(value, str):
        raise ColorError(f"color must be a string, got {type(value).__name__}: {value!r}")
    match = _HEX_RE.match(value.strip())
    if not match:
        raise ColorError(
            f"malformed color {value!r}: expected '#RRGGBB' (or '#RGB', "
            "normalized by nibble expansion)"
        )
    digits = match.group(1).lower()
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return digits


def _parse(value: str) -> tuple[int, int, int]:
    digits = strip_hex(value)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Convert ``#RRGGBB``/``#RGB`` to an ``(r, g, b)`` tuple of ints 0-255."""
    return _parse(value)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert integer channels to lowercase ``#rrggbb``, rounding/clamping."""
    channels = []
    for name, channel in (("r", r), ("g", g), ("b", b)):
        if not isinstance(channel, (int, float)) or isinstance(channel, bool):
            raise ColorError(f"{name} channel must be numeric, got {channel!r}")
        rounded = int(round(channel))
        if not -1 <= channel <= 256:  # allow float rounding slop, reject wild values
            raise ColorError(f"{name} channel out of range 0-255: {channel!r}")
        channels.append(min(255, max(0, rounded)))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def hex_to_rgb_string(value: str, separator: str = _RGB_STRING_DEFAULT_SEP) -> str:
    """Render a hex color as decimal channels, e.g. ``"21, 22, 28"``.

    kdeglobals-style schemes want ``r,g,b``; pass ``separator=","`` for no
    spaces.
    """
    return separator.join(str(c) for c in _parse(value))


def normalize_ratio(t) -> float:
    """Normalize a mix ratio to a fraction in ``[0.0, 1.0]``.

    Accepts fractions (``0.15``), percentages (``15``, ``15.5``, ``"15%"``).
    Anything outside the representable range raises ColorError.
    """
    if isinstance(t, bool):
        raise ColorError(f"mix ratio must be numeric or 'N%', got bool: {t!r}")
    if isinstance(t, str):
        text = t.strip()
        percent = text.endswith("%")
        if percent:
            text = text[:-1].strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ColorError(f"invalid mix ratio {t!r}: expected number or 'N%'") from exc
        if percent:
            value /= 100.0
        elif value > 1.0:
            # Bare numbers above 1 are treated as percentages so that both
            # `mix a b 50` and `mix a b "50%"` mean the same thing.
            value /= 100.0
    elif isinstance(t, (int, float)):
        value = float(t)
        if value > 1.0:
            value /= 100.0
    else:
        raise ColorError(f"mix ratio must be numeric or 'N%', got {type(t).__name__}: {t!r}")
    if not 0.0 <= value <= 1.0:
        raise ColorError(f"mix ratio out of range 0-100%: {t!r}")
    return value


def mix_rgb(first: str, second: str, t) -> tuple[int, int, int]:
    """Blend *second* over *first* by ratio *t* (see module docstring)."""
    fraction = normalize_ratio(t)
    a = _parse(first)
    b = _parse(second)
    return tuple(
        round((1.0 - fraction) * ac + fraction * bc) for ac, bc in zip(a, b)
    )


def mix(first: str, second: str, t) -> str:
    """Blend two colors and return the result as lowercase ``#rrggbb``."""
    return rgb_to_hex(*mix_rgb(first, second, t))


def _srgb_channel_to_linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value: str) -> float:
    """WCAG 2.x relative luminance of a hex color, in ``[0.0, 1.0]``."""
    r, g, b = _parse(value)
    linear = (
        _srgb_channel_to_linear(r),
        _srgb_channel_to_linear(g),
        _srgb_channel_to_linear(b),
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two colors; 1.0 (identical) .. 21.0."""
    l1 = relative_luminance(first)
    l2 = relative_luminance(second)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 4)
