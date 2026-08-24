"""KDE Plasma 6 environment detection for the kde adapter.

Everything here is a *pure query*: no files are written, no settings
changed, no desktop state touched. Detection results decide whether the
adapter participates on this machine (``capability``) and which native
mechanisms are safe to use.

Injection points
----------------
``env``, ``which`` and ``version_runner`` are injectable so unit tests
can simulate Plasma (or its absence) without touching the host: pass a
mapping for *env*, a callable for *which*, and a callable returning
``plasmashell --version`` output for *version_runner*.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "TOOL_PLASMA_APPLY_COLORSCHEME",
    "TOOL_PLASMA_APPLY_WALLPAPERIMAGE",
    "TOOL_KREADCONFIG6",
    "TOOL_QDBUS6",
    "PLASMA_TOOLS",
    "PlasmaEnvironment",
    "detect_plasma",
]

#: Native utilities the adapter may drive, by role.
TOOL_PLASMA_APPLY_COLORSCHEME = "plasma-apply-colorscheme"
TOOL_PLASMA_APPLY_WALLPAPERIMAGE = "plasma-apply-wallpaperimage"
TOOL_KREADCONFIG6 = "kreadconfig6"
TOOL_QDBUS6 = "qdbus6"

#: Every binary probed by :func:`detect_plasma`, in report order.
PLASMA_TOOLS: tuple[str, ...] = (
    TOOL_PLASMA_APPLY_COLORSCHEME,
    TOOL_PLASMA_APPLY_WALLPAPERIMAGE,
    TOOL_KREADCONFIG6,
    TOOL_QDBUS6,
)

_VERSION_RE = re.compile(r"plasmashell\s+(\d+)\.(\d+)(?:\.(\d+))?")

_VERSION_TIMEOUT_S = 5.0


def _default_version_runner(_argv: list[str]) -> str | None:
    """Run one version probe command; None on any failure."""
    try:
        proc = subprocess.run(
            _argv,
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None


@dataclass(frozen=True)
class PlasmaEnvironment:
    """What detection learned about this machine's Plasma installation."""

    #: ``$XDG_CURRENT_DESKTOP`` (may be a colon-separated list).
    desktop: str | None
    #: ``$XDG_SESSION_TYPE`` (``wayland`` / ``x11`` …), informational.
    session_type: str | None
    #: Parsed plasmashell version string (``"6.7.4"``), None when absent.
    plasmashell_version: str | None
    #: Tool name → absolute path (or None when not installed).
    tools: Mapping[str, str | None] = field(default_factory=dict)

    def tool_path(self, name: str) -> str | None:
        return self.tools.get(name)

    def has(self, name: str) -> bool:
        return bool(self.tools.get(name))

    @property
    def is_plasma_session(self) -> bool:
        """True when ``$XDG_CURRENT_DESKTOP`` identifies KDE Plasma."""
        return bool(self.desktop) and "kde" in self.desktop.lower()

    @property
    def major_version(self) -> int | None:
        if not self.plasmashell_version:
            return None
        match = _VERSION_RE.search(f"plasmashell {self.plasmashell_version}")
        return int(match.group(1)) if match else None


def detect_plasma(
    *,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    version_runner: Callable[[list[str]], str | None] = _default_version_runner,
) -> PlasmaEnvironment:
    """Probe the environment for a Plasma 6 session and its native tools.

    Never raises: a machine without Plasma yields an environment whose
    :attr:`is_plasma_session` is False and whose tools are missing, and
    the adapter turns that into an accurate "unsupported" capability.
    """
    environment = env if env is not None else os.environ
    tools: dict[str, str | None] = {name: which(name) for name in PLASMA_TOOLS}

    version: str | None = None
    plasmashell = which("plasmashell")
    if plasmashell:
        try:
            raw = version_runner([plasmashell, "--version"])
        except Exception:  # noqa: BLE001 — a broken probe is "unknown", not fatal
            raw = None
        if raw:
            match = _VERSION_RE.search(raw)
            if match:
                major, minor, patch = match.group(1), match.group(2), match.group(3) or "0"
                version = f"{major}.{minor}.{patch}"

    return PlasmaEnvironment(
        desktop=environment.get("XDG_CURRENT_DESKTOP"),
        session_type=environment.get("XDG_SESSION_TYPE"),
        plasmashell_version=version,
        tools=tools,
    )
