"""Konsole terminal colorscheme generation (documented profile/theme model).

Konsole stores per-profile color schemes as KConfig INI files in
``~/.local/share/konsole/*.colorscheme``; a profile selects one with
``[Appearance] ColorScheme=<name-without-extension>``. Section/key
names below were verified against a live Konsole on Plasma 6.7 (the
machine's own ``Adaptive-Plasma.colorscheme``) — nothing is invented:

* ``[General] Description/Opacity/Blur``
* ``[Background] Color=r,g,b``, ``[Foreground] Color=r,g,b``
* ``[Color0]``..``[Color7]`` and their intense variants
  ``[Color0Intense]``..``[Color7Intense]``

Mapping policy: the ANSI ramp *is* the data. Base hues map to
``[Color0..7]``, bright hues to the matching intense sections
(Konsole's "intense" == the classic bright ramp), background/foreground
to the semantic roles of the same name.
"""

from __future__ import annotations

import re

from core.color import hex_to_rgb_string
from core.errors import AdapterError

__all__ = [
    "SCHEME_ID",
    "SCHEME_FILENAME",
    "render_colorscheme",
    "parse_colorscheme",
]

#: Filename stem everywhere: file ``OmniTheme.colorscheme``,
#: profile key ``ColorScheme=OmniTheme``.
SCHEME_ID = "OmniTheme"

SCHEME_FILENAME = f"{SCHEME_ID}.colorscheme"

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")

_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")


def render_colorscheme(palette: dict[str, str]) -> str:
    """Render the Omni Konsole colorscheme INI for *palette* (role→hex)."""
    if not _SAFE_NAME_RE.match(SCHEME_ID):
        raise AdapterError(f"unsafe konsole scheme id {SCHEME_ID!r}")

    def triplet(role: str) -> str:
        value = palette.get(role)
        if not value:
            return ""
        return hex_to_rgb_string(value, separator=",")

    lines: list[str] = [
        "[General]",
        "Description=Omni Theme",
        "Opacity=1",
        "Blur=false",
        "",
        "[Background]",
    ]
    bg = triplet("background")
    if bg:
        lines.append(f"Color={bg}")
    lines += ["", "[Foreground]"]
    fg = triplet("foreground")
    if fg:
        lines.append(f"Color={fg}")

    for i in range(8):
        base = triplet(f"color{i}")
        bright = triplet(f"color{i + 8}")
        lines += ["", f"[Color{i}]"]
        if base:
            lines.append(f"Color={base}")
        lines += [f"[Color{i}Intense]"]
        if bright:
            lines.append(f"Color={bright}")
    return "\n".join(lines) + "\n"


def parse_colorscheme(text: str) -> dict[tuple[str, str], str]:
    """Parse a .colorscheme into ``((section, key), value)`` pairs."""
    result: dict[tuple[str, str], str] = {}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SECTION_RE.match(stripped)
        if match:
            section = match.group(1)
            continue
        if "=" in stripped and section:
            key, _, value = stripped.partition("=")
            result[(section, key.strip())] = value.strip()
    return result
