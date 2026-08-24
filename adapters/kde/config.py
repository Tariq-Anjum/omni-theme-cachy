"""Configuration constants and process helpers for the kde adapter.

Ownership boundary (session-05 decision)
----------------------------------------
Omni owns exactly two kinds of paths:

1. the generated Color Scheme package
   ``$XDG_DATA_HOME/color-schemes/OmniTheme.colors`` — a *generated*
   artifact, safe to write/overwrite because Omni authored its content;
2. Omni-private records under ``<state>/adapters/`` (wallpaper journal).

``~/.config/kdeglobals`` is **KDE user state** produced by applying a
scheme: ``plasma-apply-colorscheme`` copies scheme values there, hashes
them and notifies running apps. Omni never writes that file; it only
reads it back for verification.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from core.errors import AdapterError

__all__ = [
    "SCHEME_ID",
    "SCHEME_DISPLAY_NAME",
    "SAFE_ID_RE",
    "COLOR_SCHEMES_SUBDIR",
    "ADAPTER_RECORDS_SUBDIR",
    "JOURNAL_FILE",
    "RUN_TIMEOUT_S",
    "safe_scheme_id",
    "color_schemes_dir",
    "scheme_file_path",
    "journal_path",
    "run_command",
]

#: Controlled project-owned scheme id. Filename stem, ``[General]
#: ColorScheme`` value and lookup name are all this single token so
#: ``plasma-apply-colorscheme OmniTheme`` can never be ambiguous.
SCHEME_ID = "OmniTheme"

#: Human-readable display name written to ``[General] Name``.
SCHEME_DISPLAY_NAME = "Omni Theme"

#: Ids must be filename-safe: no separators, no leading dot/digit tricks.
SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")

COLOR_SCHEMES_SUBDIR = Path("color-schemes")
ADAPTER_RECORDS_SUBDIR = "adapters"
JOURNAL_FILE = "kde.json"

RUN_TIMEOUT_S = 30.0


def safe_scheme_id(scheme_id: str = SCHEME_ID) -> str:
    """Validate and return the scheme id used for file/lookup names."""
    if not SAFE_ID_RE.match(scheme_id):
        raise AdapterError(
            f"unsafe color scheme id {scheme_id!r}: must match {SAFE_ID_RE.pattern}"
        )
    return scheme_id


def color_schemes_dir() -> Path:
    """User Color Scheme directory (``$XDG_DATA_HOME/color-schemes``)."""
    from core.filesystem import xdg_data_home  # call-time resolution for tests

    return xdg_data_home() / COLOR_SCHEMES_SUBDIR


def scheme_file_path(scheme_id: str = SCHEME_ID) -> Path:
    """Full path of the Omni-generated ``.colors`` file."""
    return color_schemes_dir() / f"{safe_scheme_id(scheme_id)}.colors"


def journal_path(state_root: str | Path) -> Path:
    """Adapter-private record file under the engine state root."""
    return Path(state_root) / ADAPTER_RECORDS_SUBDIR / JOURNAL_FILE


def run_command(
    argv: list[str],
    *,
    timeout: float = RUN_TIMEOUT_S,
) -> subprocess.CompletedProcess[str]:
    """Run one native command, capturing output; never raises on exit codes.

    Raises :class:`core.errors.AdapterError` only when the binary cannot
    be executed at all (missing/cancelled/timeout) — a non-zero exit is
    a *result* the caller interprets against its own success criteria.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdapterError(f"required tool not found: {argv[0]}") from exc
    except PermissionError as exc:
        raise AdapterError(f"cannot execute {argv[0]}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(f"{argv[0]} timed out after {timeout}s") from exc
