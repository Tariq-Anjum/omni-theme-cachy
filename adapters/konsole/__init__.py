"""Konsole terminal adapter (the one explicitly supported terminal).

Exposes :class:`KonsoleAdapter` plus focused helpers:

* :mod:`adapters.konsole.colorscheme` — ANSI ramp → Konsole
  ``.colorscheme`` INI (documented profile/theme model);
* :mod:`adapters.konsole.detection` — pure Konsole probes;
* :mod:`adapters.konsole.adapter` — contract phases, byte-preserving
  profile surgery and the rollback journal.

Omni owns the generated ``OmniTheme.colorscheme``; the user's default
profile is only touched on its single ``ColorScheme`` key, journalled
for exact rollback.
"""

from __future__ import annotations

from adapters.konsole.adapter import Journal, KonsoleAdapter, KonsolePlan, journal_path
from adapters.konsole.colorscheme import SCHEME_FILENAME, SCHEME_ID, render_colorscheme
from adapters.konsole.detection import KonsoleEnvironment, detect_konsole

__all__ = [
    "KonsoleAdapter",
    "KonsolePlan",
    "Journal",
    "journal_path",
    "SCHEME_ID",
    "SCHEME_FILENAME",
    "render_colorscheme",
    "KonsoleEnvironment",
    "detect_konsole",
]
