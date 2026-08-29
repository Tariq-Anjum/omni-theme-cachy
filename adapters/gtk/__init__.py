"""GTK adapter: KDE-sync verification first, explicit direct fallback.

Exposes :class:`GtkAdapter` plus focused helpers:

* :mod:`adapters.gtk.detection` — pure GTK environment probes
  (independent from any desktop integration);
* :mod:`adapters.gtk.sync` — kdeglobals ↔ colors.css propagation check
  for KDE's kde-gtk-config pipeline (the preferred strategy);
* :mod:`adapters.gtk.direct` — opt-in, marker-owned ``gtk.css`` block
  generation with journal-backed rollback (fallback only).

The adapter never writes GTK files by default: when KDE's integration
is present it delegates and verifies; when absent it reports honestly.
"""

from __future__ import annotations

from adapters.gtk.adapter import (
    MODE_DIRECT,
    MODE_KDE_SYNC,
    MODE_OBSERVE,
    GtkAdapter,
    GtkPlan,
)
from adapters.gtk.capability import (
    MODE_KDE_NATIVE_SYNC,
    MODE_UNSUPPORTED,
    GTKCapability,
    detect_capability,
    doctor_report,
    mode_of,
)
from adapters.gtk.detection import GtkEnvironment, detect_gtk

__all__ = [
    "GtkAdapter",
    "GtkPlan",
    "GtkEnvironment",
    "detect_gtk",
    "GTKCapability",
    "detect_capability",
    "mode_of",
    "doctor_report",
    "MODE_KDE_SYNC",
    "MODE_KDE_NATIVE_SYNC",
    "MODE_DIRECT",
    "MODE_OBSERVE",
    "MODE_UNSUPPORTED",
]
