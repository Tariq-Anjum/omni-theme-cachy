"""Pure GTK environment detection for the gtk adapter.

Everything here is a *read-only query*: no settings are changed, no
files are written. Detection decides (a) whether the adapter
participates at all (``capability``) and (b) which strategy
``plan`` selects:

* **kde-sync** — KDE's own ``kde-gtk-config`` integration is present
  (``kcmshell6`` and/or the ``colorreload-gtk-module`` listed in
  ``gtk-modules``). Applying a KDE Color Scheme then updates
  ``kdeglobals``, and kde-gtk-config propagates those colors into
  ``~/.config/gtk-{3,4}.0/colors.css``. Omni must not write the same
  files independently.
* **direct** — no KDE integration; only available when explicitly
  enabled by the caller (never the default).
* **observe** — report capability, change nothing.

Injection points mirror :mod:`adapters.kde.detection`: pass *env*,
*which* and *config_home* to simulate any machine hermetically.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

__all__ = [
    "TOOL_KCMSHELL6",
    "GTK_VERSIONS",
    "GtkEnvironment",
    "detect_gtk",
    "parse_settings_ini",
]

TOOL_KCMSHELL6 = "kcmshell6"

#: Settings directories probed under ``$XDG_CONFIG_HOME``.
GTK_VERSIONS: tuple[str, ...] = ("gtk-3.0", "gtk-4.0")

#: The GTK module kde-gtk-config installs to hot-reload colors.
COLORRELOAD_MODULE = "colorreload-gtk-module"


def parse_settings_ini(text: str) -> dict[str, str]:
    """Minimal INI parse of a GTK ``settings.ini`` (single [Settings] group).

    Unknown groups are skipped; later duplicates win (KConfig semantics).
    Never raises on odd input: detection must stay informative.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("["):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


@dataclass(frozen=True)
class GtkEnvironment:
    """What detection learned about this machine's GTK setup."""

    config_home: Path
    #: ``$XDG_CURRENT_DESKTOP``, informational.
    desktop: str | None = None
    #: Absolute kcmshell6 path, or None.
    tools: Mapping[str, str | None] = field(default_factory=dict)
    #: Parsed ``settings.ini`` per version dir name.
    settings: Mapping[str, dict[str, str]] = field(default_factory=dict)

    def has(self, tool: str) -> bool:
        return bool(self.tools.get(tool))

    def dir(self, version: str) -> Path:
        return self.config_home / version

    def has_gtk(self, version: str | None = None) -> bool:
        versions = (version,) if version else GTK_VERSIONS
        return any(self.dir(v).is_dir() for v in versions)

    @property
    def gtk_theme(self) -> str | None:
        """``gtk-theme-name`` from GTK3 settings.ini (the classic signal)."""
        ini = self.settings.get("gtk-3.0") or {}
        return ini.get("gtk-theme-name")

    def gtk_modules(self, version: str = "gtk-3.0") -> list[str]:
        raw = (self.settings.get(version) or {}).get("gtk-modules", "")
        return [m for m in (part.strip() for part in raw.split(":")) if m]

    @property
    def colorreload_module_active(self) -> bool:
        """True when kde-gtk-config's reload module is in the module list."""
        return COLORRELOAD_MODULE in self.gtk_modules("gtk-3.0")

    @property
    def kde_gtk_integration(self) -> bool:
        """Signals that KDE owns GTK color propagation on this machine."""
        return self.has(TOOL_KCMSHELL6) or self.colorreload_module_active

    def colors_css(self, version: str) -> Path | None:
        path = self.dir(version) / "colors.css"
        return path if path.is_file() else None


def detect_gtk(
    *,
    env: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    config_home: Path | None = None,
) -> GtkEnvironment:
    """Probe for GTK configuration directories and KDE sync signals.

    Never raises and never writes: a machine without GTK yields an
    environment whose ``has_gtk()`` is False and whose integration
    signals are absent.
    """
    environment = env if env is not None else os.environ
    base = (
        Path(config_home)
        if config_home is not None
        else _resolve_config_home(environment)
    )
    tools = {TOOL_KCMSHELL6: which(TOOL_KCMSHELL6)}

    settings: dict[str, dict[str, str]] = {}
    for version in GTK_VERSIONS:
        ini_path = base / version / "settings.ini"
        try:
            text = ini_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        settings[version] = parse_settings_ini(text)

    return GtkEnvironment(
        config_home=base,
        desktop=environment.get("XDG_CURRENT_DESKTOP"),
        tools=tools,
        settings=settings,
    )


def _resolve_config_home(environment: Mapping[str, str]) -> Path:
    value = environment.get("XDG_CONFIG_HOME")
    if value and value.strip():
        return Path(value).expanduser()
    home = environment.get("HOME")
    if home:
        return Path(home) / ".config"
    return Path.home() / ".config"
