"""Concrete desktop adapters for omni-theme-cachy.

Each subpackage is an independent, self-contained adapter that satisfies
the :class:`core.adapters.ThemeAdapter` protocol. The core engine never
imports anything from here; composition happens at the edges (CLI,
scripts) via :func:`build_default_registry`.

Shipped adapters (session 06):

* :mod:`adapters.kde` — Plasma Color Scheme + wallpaper;
* :mod:`adapters.gtk` — KDE-sync verification (preferred) with an
  explicit opt-in direct ``gtk.css`` fallback;
* :mod:`adapters.vscode` — ``workbench.colorCustomizations`` merge;
* :mod:`adapters.konsole` — the explicitly supported terminal.
"""

from __future__ import annotations

from core.adapters import AdapterRegistry

from adapters.gtk import GtkAdapter
from adapters.kde import KdeAdapter
from adapters.konsole import KonsoleAdapter
from adapters.vscode import VscodeAdapter

__all__ = [
    "KdeAdapter",
    "GtkAdapter",
    "VscodeAdapter",
    "KonsoleAdapter",
    "build_default_registry",
]


def build_default_registry() -> AdapterRegistry:
    """Every shipped adapter, in execution order.

    Registration is unconditional; participation is decided per machine
    by each adapter's ``capability()`` probe (unsupported adapters are
    skipped and reported, never fatal). KDE runs first so the GTK
    adapter verifies propagation *after* kdeglobals was written.
    """
    registry = AdapterRegistry()
    registry.register(KdeAdapter())
    registry.register(GtkAdapter())
    registry.register(VscodeAdapter())
    registry.register(KonsoleAdapter())
    return registry
