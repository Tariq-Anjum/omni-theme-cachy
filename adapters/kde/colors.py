"""Omni palette → KDE Plasma 6 Color Scheme mapping.

The Color Scheme format is KConfig INI. Section/key names below were
verified against real Plasma 6 files on the target machine (Plasma
6.7.4: ``/usr/share/color-schemes/BreezeDark.colors`` and user-installed
schemes) — no key here is invented:

* color sets: ``Colors:{Window,View,Button,Selection,Tooltip,
  Complementary,Header}`` (Header/Complementary are Plasma 6 additions);
* per-set keys: ``BackgroundNormal``, ``BackgroundAlternate``,
  ``DecorationFocus``, ``DecorationHover``, ``Foreground{Normal,
  Inactive,Active,Link,Negative,Neutral,Positive,Visited}``;
* effect sets ``ColorEffects:{Disabled,Inactive}`` (effect parameters,
  copied verbatim from upstream — they are not theme colors);
* ``[General] ColorScheme=…`` / ``Name=…``, ``[KDE] contrast=4``,
  ``[WM]`` titlebar colors.

Mapping policy
--------------
Every Omni semantic role maps to *genuine* KDE keys or is reported as
unsupported with a reason; nothing is invented to make the table look
complete (:data:`SURFACE_UNSUPPORTED`). Surface roles come from
``surfaces.toml`` and stay adapter-neutral: only semantically meaningful
entries are consumed.

This module is the source of truth; the shipped templates under
``templates/kde/`` render exactly what :func:`expected_scheme_values`
predicts, and :func:`verify_scheme_text` re-checks generated or
installed files against that model (tests lock all three together).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Iterable

from core.color import hex_to_rgb_string

__all__ = [
    "COLOR_SETS",
    "SET_KEYS",
    "EFFECT_SECTIONS",
    "COLOR_EFFECTS_DISABLED",
    "COLOR_EFFECTS_INACTIVE",
    "KDE_COLOR_MAP",
    "POPUPS_MAP",
    "SURFACE_UNSUPPORTED",
    "MAPPED_ROLE_KEYS",
    "SchemeEntry",
    "SurfaceMapping",
    "rgb_triplet",
    "normalize_triplet",
    "parse_scheme_text",
    "expected_scheme_values",
    "elevated_background",
    "surface_mapping_report",
    "scheme_text",
    "verify_scheme_text",
]

#: Color sets a complete scheme defines (Plasma 6 order).
COLOR_SETS: tuple[str, ...] = (
    "Colors:Window",
    "Colors:View",
    "Colors:Button",
    "Colors:Selection",
    "Colors:Tooltip",
    "Colors:Complementary",
    "Colors:Header",
)

#: Keys every color set carries.
SET_KEYS: tuple[str, ...] = (
    "BackgroundNormal",
    "BackgroundAlternate",
    "DecorationFocus",
    "DecorationHover",
    "ForegroundActive",
    "ForegroundInactive",
    "ForegroundLink",
    "ForegroundNegative",
    "ForegroundNeutral",
    "ForegroundNormal",
    "ForegroundPositive",
    "ForegroundVisited",
)

#: Effect sections are upstream effect parameters, not theme data.
EFFECT_SECTIONS: tuple[str, ...] = ("ColorEffects:Disabled", "ColorEffects:Inactive")

COLOR_EFFECTS_DISABLED: tuple[tuple[str, str], ...] = (
    ("Color", "56,56,56"),
    ("ColorAmount", "0"),
    ("ColorEffect", "0"),
    ("ContrastAmount", "0.65"),
    ("ContrastEffect", "1"),
    ("IntensityAmount", "0.1"),
    ("IntensityEffect", "2"),
)

COLOR_EFFECTS_INACTIVE: tuple[tuple[str, str], ...] = (
    ("ChangeSelectionColor", "true"),
    ("Color", "112,111,110"),
    ("ColorAmount", "0.025"),
    ("ColorEffect", "2"),
    ("ContrastAmount", "0.1"),
    ("ContrastEffect", "2"),
    ("Enable", "false"),
    ("IntensityAmount", "0"),
    ("IntensityEffect", "0"),
)


def _all_sets(*keys: str) -> list[tuple[str, str]]:
    """[(set, key) for every set] — helper for whole-fleet mappings."""
    return [(s, k) for s in COLOR_SETS for k in keys]


#: Omni palette role → KDE ``(section, key)`` targets. Explicit and
#: closed: roles missing here have **no** honest Color Scheme mapping.
def _text_sets(*keys: str) -> list[tuple[str, str]]:
    """:func:`_all_sets` minus ``Colors:Selection`` (its text is special)."""
    return [
        (s, k) for s in COLOR_SETS if s != "Colors:Selection" for k in keys
    ]


KDE_COLOR_MAP: dict[str, list[tuple[str, str]]] = {
    # base surfaces & text
    "background": _all_sets("BackgroundNormal"),
    "lighter_background": _all_sets("BackgroundAlternate"),
    # Selection text is bright (it sits on the selection fill), handled below.
    "foreground": _text_sets("ForegroundNormal"),
    "muted": _text_sets("ForegroundInactive"),
    # interaction
    "accent": _all_sets("DecorationFocus", "DecorationHover", "ForegroundActive"),
    "selection": [("Colors:Selection", "BackgroundAlternate")],
    "bright_foreground": [("Colors:Selection", "ForegroundNormal")],
    # status hues → KDE's semantic foreground slots
    "success": _all_sets("ForegroundPositive"),
    "warning": _all_sets("ForegroundNeutral"),
    "error": _all_sets("ForegroundNegative"),
    "info": _all_sets("ForegroundLink"),
    "accent_secondary": _all_sets("ForegroundVisited"),
}

#: Window-manager (titlebar) colors — a separate legacy section.
_WM_MAP: dict[str, str] = {
    "activeBackground": "lighter_background",
    "activeBlend": "bright_foreground",
    "activeForeground": "bright_foreground",
    "inactiveBackground": "dark_background",
    "inactiveBlend": "dark_foreground",
    "inactiveForeground": "dark_foreground",
}

#: surfaces.toml entries with genuine Color Scheme equivalents.
POPUPS_MAP: dict[str, list[tuple[str, str]]] = {
    "popups.background": [
        ("Colors:Tooltip", "BackgroundNormal"),
        ("Colors:Complementary", "BackgroundNormal"),
    ],
}

#: Surface semantics the Color Scheme cannot express. Recorded so the
#: plan can report them honestly instead of inventing keys.
SURFACE_UNSUPPORTED: dict[str, str] = {
    "controls.normal-border": (
        "KDE Color Scheme has no control-border keys; borders belong to "
        "widget styles / Plasma Style (out of scope for this adapter)"
    ),
}


@dataclass(frozen=True)
class SchemeEntry:
    """One expected ``(section, key) → '#rrggbb'`` cell of a scheme."""

    section: str
    key: str
    role: str  # Omni role it came from
    value: str


@dataclass(frozen=True)
class SurfaceMapping:
    """Report row for one ``surfaces.toml`` entry."""

    surface: str
    #: ``direct`` | ``derived`` | ``unsupported``
    mode: str
    reason: str | None = None


def rgb_triplet(hex_color: str) -> str:
    """``#rrggbb`` → KConfig triplet ``"r,g,b"`` (upstream style)."""
    return hex_to_rgb_string(hex_color, separator=",")


def normalize_triplet(raw: str) -> str:
    """Normalize any spacing variant of an RGB triplet to ``r,g,b``."""
    return ",".join(part.strip() for part in raw.split(","))


def parse_scheme_text(text: str) -> dict[tuple[str, str], str]:
    """Parse KConfig INI into ``(section, key) → raw value``."""
    parsed: dict[tuple[str, str], str] = {}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            continue
        if "=" in stripped and section:
            key, _, value = stripped.partition("=")
            parsed[(section, key.strip())] = value.strip()
    return parsed


def elevated_background(palette: Mapping[str, str]) -> str:
    """Fallback popup surface when a theme ships no ``popups.background``."""
    from core.color import mix

    return mix(palette["background"], palette["foreground"], "0.06")


def _role(
    values: dict[tuple[str, str], SchemeEntry],
    section: str,
    key: str,
    role: str,
    palette: Mapping[str, str],
) -> None:
    values[(section, key)] = SchemeEntry(section, key, role, palette[role])


def expected_scheme_values(
    palette: Mapping[str, str],
    surfaces: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[tuple[str, str], SchemeEntry]:
    """The complete predicted scheme as ``(section, key) → entry``.

    *palette* must provide every role referenced by :data:`KDE_COLOR_MAP`
    plus ``dark_background``, ``dark_foreground``, ``bright_foreground``.
    *surfaces* (optional, ``group → key → value`` shape) contributes the
    popup elevation color when ``popups.background`` exists; otherwise a
    derived fallback is used and the affected entries carry role
    ``"<derived:popups.background>"``.
    """
    popups_bg: str | None = None
    if surfaces:
        candidate = surfaces.get("popups", {}).get("background")
        if isinstance(candidate, str):
            popups_bg = candidate

    values: dict[tuple[str, str], SchemeEntry] = {}
    for role, targets in KDE_COLOR_MAP.items():
        for section, key in targets:
            _role(values, section, key, role, palette)

    accent = palette["accent"]

    # Selection fill uses the dedicated Omni `selection` role; its normal
    # text is the bright variant (mapped above); alternates stay quiet.
    values[("Colors:Selection", "BackgroundNormal")] = SchemeEntry(
        "Colors:Selection", "BackgroundNormal", "selection", palette["selection"]
    )

    popup_role = "popups.background" if popups_bg else "<derived:popups.background>"
    popup_value = popups_bg or elevated_background(palette)
    for section, key in POPUPS_MAP["popups.background"]:
        values[(section, key)] = SchemeEntry(section, key, popup_role, popup_value)
    values[("Colors:Tooltip", "BackgroundAlternate")] = SchemeEntry(
        "Colors:Tooltip", "BackgroundAlternate", popup_role, popup_value
    )
    values[("Colors:Complementary", "BackgroundAlternate")] = SchemeEntry(
        "Colors:Complementary", "BackgroundAlternate", popup_role, popup_value
    )

    # DecorationFocus/Hover keep the accent even inside Selection.
    for section in COLOR_SETS:
        for key in ("DecorationFocus", "DecorationHover"):
            values[(section, key)] = SchemeEntry(section, key, "accent", accent)

    for wm_key, role in _WM_MAP.items():
        values[("WM", wm_key)] = SchemeEntry("WM", wm_key, role, palette[role])

    return values


def surface_mapping_report(
    surfaces: Mapping[str, Mapping[str, object]] | None,
) -> tuple[SurfaceMapping, ...]:
    """Honest per-entry report of how ``surfaces.toml`` was consumed."""
    rows: list[SurfaceMapping] = []
    popup_present = bool(surfaces and surfaces.get("popups", {}).get("background"))
    rows.append(
        SurfaceMapping(
            surface="popups.background",
            mode="direct" if popup_present else "derived",
            reason=None
            if popup_present
            else "theme ships no [popups] background; elevated surface "
            "derived by mixing background toward foreground",
        )
    )
    focus_present = bool(surfaces and surfaces.get("controls", {}).get("focus-border"))
    rows.append(
        SurfaceMapping(
            surface="controls.focus-border",
            mode="semantic",
            reason=(
                "gradient flattened to the solid accent on DecorationFocus/"
                "DecorationHover; Qt color schemes cannot express gradients"
            )
            if focus_present
            else "focus/hover decorations take the palette accent",
        )
    )
    for surface, why in SURFACE_UNSUPPORTED.items():
        rows.append(SurfaceMapping(surface=surface, mode="unsupported", reason=why))
    return tuple(rows)


def scheme_text(
    *,
    name: str,
    display_name: str,
    values: Mapping[tuple[str, str], str],
    contrast: int = 4,
) -> str:
    """Serialize a full ``.colors`` document from ``(section, key)`` pairs.

    *values* maps the same keys :func:`expected_scheme_values` produces.
    Values may be ``#rrggbb`` hex or ``r,g,b`` triplets (spaced or
    compact) — everything is normalized to compact KConfig triplets.
    Sections are emitted in Plasma 6 order with sorted keys, mirroring
    upstream files.
    """
    lines: list[str] = []

    def emit(section: str, pairs: Iterable[tuple[str, str]]) -> None:
        lines.append(f"[{section}]")
        lines.extend(f"{key}={value}" for key, value in sorted(pairs))
        lines.append("")

    for section, pairs in (
        ("ColorEffects:Disabled", COLOR_EFFECTS_DISABLED),
        ("ColorEffects:Inactive", COLOR_EFFECTS_INACTIVE),
    ):
        emit(section, pairs)

    grouped: dict[str, list[tuple[str, str]]] = {}
    for (section, key), value in values.items():
        if value.startswith("#"):
            value = rgb_triplet(value)
        grouped.setdefault(section, []).append((key, normalize_triplet(value)))
    for section in COLOR_SETS:
        emit(section, grouped.get(section, []))

    emit(
        "General",
        [("ColorScheme", name), ("Name", display_name)],
    )
    emit("KDE", [("contrast", str(contrast))])
    emit("WM", grouped.get("WM", []))
    return "\n".join(lines).rstrip() + "\n"


def verify_scheme_text(
    text: str,
    palette: Mapping[str, str],
    surfaces: Mapping[str, Mapping[str, object]] | None = None,
) -> list[str]:
    """Compare a rendered/installed scheme against the model.

    Returns a list of human-readable mismatches (empty when faithful).
    Comparison normalizes triplet spacing so template output style stays
    free to differ cosmetically from upstream file style.
    """
    actual = parse_scheme_text(text)
    problems: list[str] = []
    for (section, key), entry in expected_scheme_values(palette, surfaces).items():
        found = actual.get((section, key))
        if found is None:
            problems.append(f"missing [{section}] {key}")
            continue
        expected_raw = normalize_triplet(rgb_triplet(entry.value))
        if normalize_triplet(found) != expected_raw:
            problems.append(
                f"[{section}] {key}: expected {expected_raw}, "
                f"found {normalize_triplet(found)}"
            )
    general_name = actual.get(("General", "ColorScheme"))
    if general_name is None:
        problems.append("missing [General] ColorScheme")
    return problems


#: Every palette role the model consumes (documentation + tests).
MAPPED_ROLE_KEYS: tuple[str, ...] = tuple(
    sorted(set(KDE_COLOR_MAP) | set(_WM_MAP.values()) | {"selection"})
)
