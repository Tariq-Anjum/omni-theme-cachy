"""KDE Plasma 6 adapter (session 05): Color Scheme + wallpaper.

Exposes :class:`KdeAdapter` (the :class:`core.adapters.ThemeAdapter`
implementation) plus focused helpers:

* :mod:`adapters.kde.colors` — palette → Color Scheme mapping model;
* :mod:`adapters.kde.wallpaper` — cache/journal/backend plumbing;
* :mod:`adapters.kde.detection` — pure Plasma environment probes;
* :mod:`adapters.kde.config` — owned paths and process helpers.

Plasma Style (``~/.local/share/plasma/desktoptheme/``) and Global Theme
(look-and-feel) are explicitly **out of scope** here; they get their own
adapters in later sessions.
"""

from __future__ import annotations

from adapters.kde.adapter import KdeAdapter, KdePlan
from adapters.kde.detection import PlasmaEnvironment, detect_plasma

__all__ = ["KdeAdapter", "KdePlan", "PlasmaEnvironment", "detect_plasma"]
