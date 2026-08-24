"""Concrete desktop adapters for omni-theme-cachy.

Each subpackage is an independent, self-contained adapter that satisfies
the :class:`core.adapters.ThemeAdapter` protocol. The core engine never
imports anything from here; composition happens at the edges (CLI,
scripts) via :func:`build_default_registry`.
"""

from __future__ import annotations

from core.adapters import AdapterRegistry

from adapters.kde import KdeAdapter

__all__ = ["KdeAdapter", "build_default_registry"]


def build_default_registry() -> AdapterRegistry:
    """Every shipped adapter, in execution order.

    Registration is unconditional; participation is decided per machine
    by each adapter's ``capability()`` probe (unsupported adapters are
    skipped and reported, never fatal).
    """
    registry = AdapterRegistry()
    registry.register(KdeAdapter())
    return registry
