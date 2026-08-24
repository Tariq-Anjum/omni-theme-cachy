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

Gradients
---------
:func:`parse_gradient` parses Omarchy-style gradient strings::

    "rgba(33ccffee) rgba(00ff99ee) 45deg"

Each stop is ``rgba(RRGGBBAA)`` (8 hex digits inside the parentheses —
hex, *not* decimal) or a plain ``#RRGGBB``; two or more stops are
required; an optional trailing angle accepts ``45deg``, ``-45deg``, or a
bare number (degrees). Results are immutable
:class:`GradientStop`/:class:`Gradient` values with alpha as a fraction
(plus ``alpha_byte``/``alpha_hex`` renderers).

Border widths
-------------
:func:`parse_border_width` parses CSS-style shorthand lists into a
:class:`BorderWidth` named tuple ordered ``(top, right, bottom, left)``:
``2``, ``"2 4"``, ``"2 4 6"``, ``"2 4 6 8"``. Values are non-negative
integers (pixels).

Surface values
--------------
:func:`classify_surface_value` / :func:`validate_surface_value` give the
loader and validator one shared notion of what may appear in
``surfaces.toml``: colors (``#…``), gradients, border widths (keys
ending in ``-width``), alpha companions (keys ending in ``-alpha``, value
in ``[0, 1]``), and plain non-negative integers for other keys.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from core.errors import ColorError, SurfaceValueError

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
    "GradientStop",
    "Gradient",
    "BorderWidth",
    "parse_gradient",
    "parse_border_width",
    "classify_surface_value",
    "validate_surface_value",
]

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_RGBA_STOP_RE = re.compile(r"^rgba\(\s*([0-9a-fA-F]{8})\s*\)$", re.IGNORECASE)
_ANGLE_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(?:deg)?$", re.IGNORECASE)
_WIDTH_TOKEN_RE = re.compile(r"^\d+$")
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


# ---------------------------------------------------------------------------
# Gradients (Omarchy-style: "rgba(33ccffee) rgba(00ff99ee) 45deg")
# ---------------------------------------------------------------------------


class GradientStop(NamedTuple):
    """One gradient stop: opaque color plus alpha as a fraction in [0, 1]."""

    color: str  # canonical "#rrggbb"
    alpha: float

    @property
    def alpha_byte(self) -> int:
        """Alpha as 0-255 (e.g. ``ee`` → 238)."""
        return round(self.alpha * 255)

    @property
    def alpha_hex(self) -> str:
        """Alpha as two lowercase hex digits (``ee``)."""
        return f"{self.alpha_byte:02x}"


class Gradient(NamedTuple):
    """A parsed gradient: ≥2 stops and an optional angle in degrees."""

    stops: tuple[GradientStop, ...]
    angle: float | None  # degrees, clockwise-from-to-top convention; None = unset

    def __str__(self) -> str:
        """Round-trip to the Omarchy text form (angle omitted when unset)."""
        parts = []
        for stop in self.stops:
            digits = strip_hex(stop.color) + stop.alpha_hex
            parts.append(f"rgba({digits})")
        if self.angle is not None:
            angle = int(self.angle) if self.angle.is_integer() else self.angle
            parts.append(f"{angle}deg")
        return " ".join(parts)


def _parse_gradient_stop(token: str) -> GradientStop:
    rgba = _RGBA_STOP_RE.match(token)
    if rgba:
        digits = rgba.group(1).lower()
        return GradientStop(
            color=f"#{digits[0:6]}",
            alpha=int(digits[6:8], 16) / 255.0,
        )
    try:  # plain "#rrggbb" / "#rgb" stop with full opacity
        return GradientStop(color=f"#{strip_hex(token)}", alpha=1.0)
    except ColorError:
        raise SurfaceValueError(
            f"bad gradient stop {token!r}: expected 'rgba(RRGGBBAA)' or '#RRGGBB'"
        ) from None


def parse_gradient(text: str) -> Gradient:
    """Parse an Omarchy-style gradient string into a :class:`Gradient`.

    Accepts 2+ stops (``rgba(RRGGBBAA)`` or ``#RRGGBB``/``#RGB`` each)
    and one optional trailing angle (``45deg``, ``45``, ``-30.5deg``).
    Raises SurfaceValueError on any deviation.
    """
    if not isinstance(text, str):
        raise SurfaceValueError(
            f"gradient must be a string, got {type(text).__name__}: {text!r}"
        )
    tokens = text.split()
    if len(tokens) < 2:
        raise SurfaceValueError(
            f"gradient {text!r} needs at least two stops "
            "(for a single translucent color use a '<key>-alpha' companion)"
        )

    angle: float | None = None
    if _ANGLE_RE.match(tokens[-1]):
        angle = float(_ANGLE_RE.match(tokens[-1]).group(1))
        tokens = tokens[:-1]

    if len(tokens) < 2:
        raise SurfaceValueError(f"gradient {text!r} needs at least two color stops")

    stops = tuple(_parse_gradient_stop(token) for token in tokens)
    return Gradient(stops=stops, angle=angle)


# ---------------------------------------------------------------------------
# Border widths (CSS-style shorthand)
# ---------------------------------------------------------------------------


class BorderWidth(NamedTuple):
    """CSS-style border width expanded to ``(top, right, bottom, left)``."""

    top: int
    right: int
    bottom: int
    left: int


def parse_border_width(value) -> BorderWidth:
    """Parse CSS-style shorthand into :class:`BorderWidth` sides.

    Accepts a non-negative int or a string of 1–4 whitespace-separated
    non-negative integers (``"2"``, ``"2 4"``, ``"2 4 6"``, ``"2 4 6 8"``),
    expanded per CSS shorthand rules. Anything else raises
    SurfaceValueError.
    """
    if isinstance(value, bool):
        raise SurfaceValueError(f"border-width must be int or string, got bool")
    if isinstance(value, int):
        tokens = [str(value)]
    elif isinstance(value, str):
        tokens = value.split()
    else:
        raise SurfaceValueError(
            f"border-width must be int or string, got {type(value).__name__}: {value!r}"
        )

    if not 1 <= len(tokens) <= 4:
        raise SurfaceValueError(
            f"border-width {value!r}: expected 1-4 values, got {len(tokens)}"
        )
    for token in tokens:
        if not _WIDTH_TOKEN_RE.match(token):
            raise SurfaceValueError(
                f"border-width {value!r}: {token!r} is not a non-negative integer"
            )

    numbers = [int(t) for t in tokens]
    match len(numbers):
        case 1:
            t = r = b = l = numbers[0]
        case 2:
            t = b = numbers[0]
            r = l = numbers[1]
        case 3:
            t, r, b = numbers
            l = r
        case _:
            t, r, b, l = numbers
    return BorderWidth(top=t, right=r, bottom=b, left=l)


# ---------------------------------------------------------------------------
# Surface-role values (surfaces.toml)
# ---------------------------------------------------------------------------


def classify_surface_value(key: str, value) -> str:
    """Classify a surfaces.toml entry as a value kind.

    Returns one of ``"color"``, ``"gradient"``, ``"border-width"``,
    ``"alpha"``, ``"number"`` — or raises SurfaceValueError when the
    value matches no accepted form for its key.

    Rules (mirroring Omarchy's surface language, documented in this
    module's docstring):

    * keys ending ``-width`` → border width (int or 1-4-int list);
    * keys ending ``-alpha`` → number in [0, 1];
    * strings starting ``#`` → single color;
    * other multi-token strings → gradient;
    * bare non-negative ints → generic dimensions/padding.
    """
    if isinstance(key, str) and key.endswith("-width"):
        parse_border_width(value)  # raises on malformed
        return "border-width"
    if isinstance(key, str) and key.endswith("-alpha"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SurfaceValueError(f"{key!r} must be a number in [0, 1], got {value!r}")
        if not 0.0 <= value <= 1.0:
            raise SurfaceValueError(f"{key!r} must be in [0, 1], got {value!r}")
        return "alpha"
    if isinstance(value, bool):
        raise SurfaceValueError(f"{key!r}: booleans are not surface values")
    if isinstance(value, int):
        if value < 0:
            raise SurfaceValueError(f"{key!r} must be non-negative, got {value!r}")
        return "number"
    if isinstance(value, float):
        raise SurfaceValueError(
            f"{key!r}: floats are ambiguous; write a string ('0.5') or an int"
        )
    if not isinstance(value, str) or not value.strip():
        raise SurfaceValueError(
            f"{key!r}: expected color, gradient or width string, got {value!r}"
        )

    text = value.strip()
    if text.startswith("#"):
        try:
            strip_hex(text)
        except ColorError as exc:  # surface values report via SurfaceValueError
            raise SurfaceValueError(f"{key!r}: {exc}") from None
        return "color"
    if " " in text or "(" in text:
        try:
            parse_gradient(text)  # raises SurfaceValueError on malformed
        except SurfaceValueError as exc:
            raise SurfaceValueError(f"{key!r}: {exc}") from None
        return "gradient"
    raise SurfaceValueError(
        f"{key!r}: {text!r} is neither a '#RRGGBB' color nor a gradient "
        "(gradients look like: rgba(33ccffee) rgba(00ff99ee) 45deg)"
    )


def validate_surface_value(key: str, value) -> None:
    """Raise SurfaceValueError unless *key*/*value* is an accepted pair."""
    classify_surface_value(key, value)
