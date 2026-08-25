"""Pure Konsole environment detection (read-only, injectable).

Probes:

* the ``konsole`` binary;
* the user profile directory ``~/.local/share/konsole`` (or
  ``$XDG_DATA_HOME/konsole``);
* ``konsolerc``'s ``[Desktop Entry] DefaultProfile=…`` key.

No settings are read through external tools and nothing is written:
``konsolerc`` is parsed directly so detection works identically on any
machine and in tests.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

__all__ = ["KonsoleEnvironment", "detect_konsole", "parse_ini"]

PROFILES_DIRNAME = "konsole"
KONSOLERC = "konsolerc"
DEFAULT_PROFILE_KEY = ("Desktop Entry", "DefaultProfile")


def parse_ini(text: str) -> dict[tuple[str, str], str]:
    """Parse a KConfig-style INI into ``((group, key), value)`` pairs."""
    result: dict[tuple[str, str], str] = {}
    group = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
            continue
        if "=" in stripped and group:
            key, _, value = stripped.partition("=")
            result[(group, key.strip())] = value.strip()
    return result


@dataclass(frozen=True)
class KonsoleEnvironment:
    """What detection learned about this machine's Konsole install."""

    #: Absolute ``konsole`` binary path, or None.
    binary: str | None
    profiles_dir: Path | None
    config_home: Path
    #: Raw parsed konsolerc entries (empty when the file is absent).
    konsolerc: Mapping[tuple[str, str], str] = field(default_factory=dict)

    @property
    def default_profile(self) -> str | None:
        """``[Desktop Entry] DefaultProfile`` value (e.g. ``ZSH.profile``)."""
        value = self.konsolerc.get(DEFAULT_PROFILE_KEY)
        return value or None

    def profile_path(self) -> Path | None:
        """Absolute path of the default profile file, when it exists."""
        name = self.default_profile
        if not name or self.profiles_dir is None:
            return None
        candidate = self.profiles_dir / name
        return candidate if candidate.is_file() else None

    @property
    def installed(self) -> bool:
        return bool(self.binary) or (self.profiles_dir is not None and self.profiles_dir.is_dir())


def detect_konsole(
    *,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    config_home: Path | None = None,
    data_home: Path | None = None,
) -> KonsoleEnvironment:
    """Probe for Konsole; never raises, never writes."""
    environment = env if env is not None else os.environ

    base_config = (
        Path(config_home)
        if config_home is not None
        else _resolve_xdg(environment, "XDG_CONFIG_HOME", ".config")
    )
    base_data = (
        Path(data_home)
        if data_home is not None
        else _resolve_xdg(environment, "XDG_DATA_HOME", os.path.join(".local", "share"))
    )

    rc_path = base_config / KONSOLERC
    try:
        rc_entries = parse_ini(rc_path.read_text(encoding="utf-8"))
    except OSError:
        rc_entries = {}

    profiles_dir = base_data / PROFILES_DIRNAME
    return KonsoleEnvironment(
        binary=which("konsole"),
        profiles_dir=profiles_dir,
        config_home=base_config,
        konsolerc=rc_entries,
    )


def _resolve_xdg(environment: Mapping[str, str], var: str, default_suffix: str) -> Path:
    value = environment.get(var)
    if value and value.strip():
        return Path(value).expanduser()
    home = environment.get("HOME")
    if home:
        return Path(home) / default_suffix
    return Path.home() / default_suffix
