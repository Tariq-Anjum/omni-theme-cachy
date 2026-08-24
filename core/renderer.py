"""Deterministic template rendering for omni-theme-cachy.

Templates are inert UTF-8 text with ``{{ … }}`` expressions. Rendering is
pure substitution over a closed set of helpers — no code execution, no
imports, no control flow — so third-party templates cannot do anything
but arrange colors.

Expression grammar (whitespace-tolerant; ``{{`` is reserved)
-------------------------------------------------------------

==========================  ==============================================
``{{ key }}``               palette role or surface value
                            (``accent``, ``popups.background``, …)
``{{ key_strip }}``         hex digits without ``#`` (``4f9eea``)
``{{ key_rgb }}``           decimal channels (``79, 158, 234``)
``{{ mix A B T }}``         blend B over A by T → ``#rrggbb``
``{{ mix_strip A B T }}``   blend → hex digits without ``#``
``{{ mix_rgb A B T }}``     blend → decimal channels
``{{ kde_gradient REF }}``  surfaces gradient REF → Qt/QSS
                            ``qlineargradient(…)`` expression
==========================  ==============================================

* *KEY* may be any palette role or any dotted ``group.key`` surface
  entry. An explicit key always wins over suffix decomposition: if a
  theme defines ``foo_rgb`` it is used verbatim before ``foo`` +
  ``_rgb`` is considered.
* *A*/*B* in mixes are keys **or** literal ``#RRGGBB`` colors. *T*
  accepts everything :func:`core.color.normalize_ratio` does
  (``0.15``, ``15``, ``"15%"``).
* ``kde_gradient`` maps an Omarchy-style gradient string (as stored in
  ``surfaces.toml``) onto Qt Style Sheet syntax::

      qlineargradient(x1:0, y1:0, x2:0, y2:1,
                      stop:0 rgba(51, 204, 255, 93%),
                      stop:1 rgba(0, 255, 153, 93%))

  Angles follow the CSS convention (clockwise, ``0deg`` = to top); a
  gradient without an angle defaults to top→bottom. Stop positions are
  evenly distributed; alpha is emitted as a percentage, which Qt and
  CSS interpret identically.

Strictness
----------
Every expression must resolve. Unknown variables, malformed helpers,
unclosed ``{{`` and unrenderable values raise
:class:`core.errors.RenderError` naming the template, the line and the
expression — nothing ever silently expands to an empty string.

Template resolution order (highest precedence first)
----------------------------------------------------

1. ``~/.config/omni-theme/templates/<name>``   — user override
2. ``<theme>/templates/<name>``                — theme-specific
3. ``templates/default/<name>``                — built-in

The first existing file wins (Omarchy rule); see :func:`resolve_template`.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass
from pathlib import Path

from core.color import (
    parse_gradient,
    strip_hex,
    hex_to_rgb_string,
    mix,
)
from core.errors import RenderError, TemplateNotFoundError
from core.theme_loader import load_theme
from core.theme_model import Theme

__all__ = [
    "EXPRESSION_RE",
    "ResolvedTemplate",
    "TEMPLATE_ORIGIN_USER",
    "TEMPLATE_ORIGIN_THEME",
    "TEMPLATE_ORIGIN_BUILTIN",
    "DEFAULT_BUILTIN_TEMPLATE_ROOT",
    "build_context",
    "render_text",
    "render_template_file",
    "resolve_template",
]

#: One ``{{ … }}`` expression (non-greedy body).
EXPRESSION_RE = re.compile(r"\{\{(.*?)\}\}")

#: Token charset inside an expression: no whitespace, no braces.
_TOKEN_RE = re.compile(r"[^\s{}]+")

_MIX_OUTPUTS = {"mix": "hex", "mix_strip": "strip", "mix_rgb": "rgb"}
_STRIP_SUFFIX = "_strip"
_RGB_SUFFIX = "_rgb"

TEMPLATE_ORIGIN_USER = "user"
TEMPLATE_ORIGIN_THEME = "theme"
TEMPLATE_ORIGIN_BUILTIN = "builtin"

DEFAULT_BUILTIN_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "default"


@dataclass(frozen=True)
class ResolvedTemplate:
    """A template name pinned to an actual file and its provenance."""

    path: Path
    #: One of ``user`` / ``theme`` / ``builtin`` (highest precedence won).
    origin: str


# ---------------------------------------------------------------------------
# Context construction
# ---------------------------------------------------------------------------


def build_context(theme: Theme) -> dict[str, object]:
    """Flatten a theme into the template variable namespace.

    Palette roles appear verbatim; surface entries are namespaced as
    ``group.key``. TOML cannot produce dotted *bare* color keys, so the
    two namespaces cannot collide.
    """
    ctx: dict[str, object] = {}
    for role, value in theme.palette.items():
        ctx[role] = value
    for group, entries in theme.surfaces.items():
        for key, value in entries.items():
            ctx[f"{group}.{key}"] = value
    return ctx


# ---------------------------------------------------------------------------
# Expression evaluation
# ---------------------------------------------------------------------------


def _fmt_number(value: float) -> str:
    """Compact fixed-point rendering: ``0``, ``0.5``, ``0.25`` …"""
    if abs(value) < 1e-9:
        return "0"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def _unknown_variable(token: str, expr: str, ctx: dict[str, object]) -> RenderError:
    names = sorted(ctx)
    sample = ", ".join(names[:10])
    more = f" … (+{len(names) - 10} more)" if len(names) > 10 else ""
    return RenderError(
        f"unknown variable {token!r} in {{{{ {expr} }}}}; "
        f"defined variables ({len(names)}): {sample}{more}"
    )


def _lookup(token: str, expr: str, ctx: dict[str, object]) -> tuple[object, bool]:
    """Resolve one variable token → ``(value, was_derived_via_suffix)``."""
    if token in ctx:
        return ctx[token], False
    if token.endswith(_STRIP_SUFFIX):
        base = token[: -len(_STRIP_SUFFIX)]
        if base in ctx:
            return strip_hex(_as_color(ctx[base], token, expr)), True
    if token.endswith(_RGB_SUFFIX):
        base = token[: -len(_RGB_SUFFIX)]
        if base in ctx:
            return _as_color_text(ctx[base], token, expr, hex_to_rgb_string), True
    raise _unknown_variable(token, expr, ctx)


def _as_color(value: object, token: str, expr: str) -> str:
    """Coerce a context value to canonical ``#rrggbb`` or fail strictly."""
    if isinstance(value, str):
        candidate = value if value.startswith("#") else f"#{value}"
        try:
            return f"#{strip_hex(candidate)}"
        except Exception as exc:
            raise RenderError(
                f"{token!r} in {{{{ {expr} }}}} is not a color: {exc}"
            ) from None
    raise RenderError(
        f"{token!r} in {{{{ {expr} }}}} needs a color, got "
        f"{type(value).__name__}: {value!r}"
    )


def _as_color_text(value: object, token: str, expr: str, fn) -> str:
    return fn(_as_color(value, token, expr))


def _color_operand(token: str, expr: str, ctx: dict[str, object]) -> str:
    """Mix operand: literal ``#hex`` or any variable resolving to a color."""
    if token.startswith("#"):
        return _as_color(token, token, expr)
    value, _derived = _lookup(token, expr, ctx)
    return _as_color(value, token, expr)


def _eval_expression(expr: str, ctx: dict[str, object]) -> str:
    tokens = _TOKEN_RE.findall(expr)
    if not tokens:
        raise RenderError("empty expression")

    head = tokens[0]
    if head in _MIX_OUTPUTS:
        if len(tokens) != 4:
            raise RenderError(
                f"{head} takes exactly 3 arguments "
                f"(first, second, ratio), got {len(tokens) - 1}: {{{{ {expr} }}}}"
            )
        first = _color_operand(tokens[1], expr, ctx)
        second = _color_operand(tokens[2], expr, ctx)
        try:
            blended = mix(first, second, tokens[3])
        except Exception as exc:
            raise RenderError(f"bad ratio {tokens[3]!r} in {{{{ {expr} }}}}: {exc}") from None
        if head == "mix":
            return blended
        if head == "mix_strip":
            return strip_hex(blended)
        return hex_to_rgb_string(blended)

    if head == "kde_gradient":
        if len(tokens) != 2:
            raise RenderError(
                f"kde_gradient takes exactly 1 argument (surface reference), "
                f"got {len(tokens) - 1}: {{{{ {expr} }}}}"
            )
        value, _derived = _lookup(tokens[1], expr, ctx)
        if not isinstance(value, str):
            raise RenderError(
                f"kde_gradient needs a gradient string for {tokens[1]!r}, got "
                f"{type(value).__name__}: {value!r}"
            )
        return _qss_gradient(value, tokens[1], expr)

    if len(tokens) != 1:
        raise RenderError(
            f"cannot evaluate {{{{ {expr} }}}}: expected a variable or a "
            f"helper call (mix / mix_strip / mix_rgb / kde_gradient)"
        )

    value, _derived = _lookup(head, expr, ctx)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _fmt_number(value)
    return str(value)


def _qss_geometry(angle: float) -> str:
    """Map a CSS-convention angle onto qlineargradient endpoints.

    Principal angles (multiples of 45°, matched within 0.05°) snap to
    canonical corner-to-corner geometry so common themes read cleanly::

        0deg → x1:0 y1:1 x2:0 y2:0      (to top)
        180deg → x1:0 y1:0 x2:0 y2:1    (to bottom)

    Arbitrary angles use the exact trigonometric line through the box
    center. Angles are clockwise, ``0deg`` = to top.
    """
    principal = {
        0: (0, 1, 0, 0),
        45: (0, 1, 1, 0),
        90: (0, 0, 1, 0),
        135: (0, 0, 1, 1),
        180: (0, 0, 0, 1),
        225: (1, 0, 0, 1),
        270: (1, 0, 0, 0),
        315: (1, 1, 0, 0),
    }
    nearest = round(angle / 45.0) * 45.0
    key = int(nearest) % 360
    if abs(angle - nearest) <= 0.05 and key in principal:
        x1, y1, x2, y2 = principal[key]
        return f"x1:{x1}, y1:{y1}, x2:{x2}, y2:{y2}"

    rad = math.radians(angle)
    dx, dy = math.sin(rad), -math.cos(rad)
    x1, y1 = 0.5 - dx / 2, 0.5 - dy / 2
    x2, y2 = 0.5 + dx / 2, 0.5 + dy / 2
    return (
        f"x1:{_fmt_number(x1)}, y1:{_fmt_number(y1)}, "
        f"x2:{_fmt_number(x2)}, y2:{_fmt_number(y2)}"
    )


def _qss_gradient(text: str, token: str, expr: str) -> str:
    """Render an Omarchy gradient string as a Qt Style Sheet gradient."""
    try:
        gradient = parse_gradient(text)
    except Exception as exc:
        raise RenderError(
            f"kde_gradient: {token!r} in {{{{ {expr} }}}}: {exc}"
        ) from None

    stops = []
    last = len(gradient.stops) - 1
    for index, stop in enumerate(gradient.stops):
        digits = strip_hex(stop.color)
        r, g, b = int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)
        alpha_pct = min(100, max(0, round(stop.alpha_byte * 100 / 255)))
        stops.append(
            f"stop:{_fmt_number(index / last)} rgba({r}, {g}, {b}, {alpha_pct}%)"
        )

    angle = gradient.angle if gradient.angle is not None else 180.0
    return f"qlineargradient({_qss_geometry(angle)}, {', '.join(stops)})"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_text(
    text: str,
    context: dict[str, object] | Theme | str | Path,
    *,
    name: str = "<text>",
) -> str:
    """Render template *text* against *context*.

    *context* may be a :class:`~core.theme_model.Theme`, a flat variable
    dict (as produced by :func:`build_context`), or a path to a theme
    directory (convenience; loaded via :mod:`core.theme_loader`).

    Raises :class:`core.errors.RenderError` for any unknown variable,
    malformed expression or unclosed ``{{`` — always with template name
    and 1-based line number.
    """
    if isinstance(context, Theme):
        context = build_context(context)
    elif isinstance(context, (str, Path)):
        context = build_context(load_theme(context))

    def _replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        line = text.count("\n", 0, match.start()) + 1
        try:
            return _eval_expression(expr, context)
        except RenderError as exc:
            raise RenderError(f"{name}:{line}: {exc}") from None
        except Exception as exc:
            raise RenderError(f"{name}:{line}: {{{{ {expr} }}}}: {exc}") from None

    rendered = EXPRESSION_RE.sub(_replace, text)

    # Strictness: an unclosed '{{' must fail, never pass through as text.
    last_end = max((m.end() for m in EXPRESSION_RE.finditer(text)), default=0)
    dangling = text.find("{{", last_end)
    if dangling != -1 and text.find("}}", dangling + 2) == -1:
        line = text.count("\n", 0, dangling) + 1
        raise RenderError(
            f"{name}:{line}: unclosed expression — "
            + "'{{' without matching '}}'"
        )
    return rendered


def render_template_file(
    path: str | Path,
    context: dict[str, object] | Theme,
) -> str:
    """Read a template file (UTF-8) and :func:`render_text` it."""
    template_path = Path(path)
    try:
        text = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError(f"cannot read template {template_path}: {exc}") from exc
    return render_text(text, context, name=str(template_path))


def resolve_template(
    name: str,
    *,
    theme_dir: str | Path | None = None,
    user_templates_dir: str | Path | None = None,
    builtin_root: str | Path | None = None,
) -> ResolvedTemplate:
    """Resolve a template *name* through the precedence chain.

    Highest wins: user dir → theme's ``templates/`` → built-in default
    root. *name* may contain subdirectories (``kde/colors.tpl``).
    Raises :class:`core.errors.TemplateNotFoundError` naming every
    location searched.
    """
    if not name or Path(name).is_absolute():
        raise TemplateNotFoundError(
            f"template name must be relative to its root, got {name!r}"
        )

    roots: list[tuple[str, Path]] = []
    if user_templates_dir is not None:
        roots.append((TEMPLATE_ORIGIN_USER, Path(user_templates_dir)))
    if theme_dir is not None:
        roots.append((TEMPLATE_ORIGIN_THEME, Path(theme_dir) / "templates"))
    effective_builtin = (
        Path(builtin_root) if builtin_root is not None else DEFAULT_BUILTIN_TEMPLATE_ROOT
    )
    roots.append((TEMPLATE_ORIGIN_BUILTIN, effective_builtin))

    searched = []
    for origin, root in roots:
        candidate = root / name
        searched.append(str(candidate))
        if candidate.is_file():
            return ResolvedTemplate(path=candidate, origin=origin)

    raise TemplateNotFoundError(
        f"template {name!r} not found; searched: " + "; ".join(searched)
    )
