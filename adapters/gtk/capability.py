"""Structured GTK capability classification (session 11).

Answers one question read-only: *what can Omni honestly do about GTK
theming on this machine?* Detection here never modifies a file; the
live system is ground truth — a signal counts only when it is actually
present (a binary on PATH, a module listed in ``settings.ini``), not
because documentation says it usually exists.

Ownership model
---------------
Four distinct authorities exist around GTK theming and they must not
be conflated:

1. Omni-owned — the *generated color scheme* handed to KDE (and, on
   machines without KDE's sync, an explicitly opted-in managed block
   inside ``gtk-3.0/gtk.css``);
2. KDE-owned — ``kdeglobals`` and everything kde-gtk-config derives
   from it (``gtk-{3,4}.0/colors.css``, the recorded ``gtk-theme-name``);
3. KDE's GTK-sync output — exactly that ``colors.css`` propagation;
4. User-owned — any GTK customization outside Omni's markers, including
   a deliberately chosen non-Breeze GTK theme.

Omni therefore never claims the GTK files wholesale. When KDE's
mechanism is present the adapter's behavior is detect + verify +
report (:data:`MODE_KDE_NATIVE_SYNC`); independent writes would fight
KDE for the same files.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.gtk.detection import GtkEnvironment

__all__ = [
    "MODE_KDE_NATIVE_SYNC",
    "MODE_DIRECT",
    "MODE_UNSUPPORTED",
    "GTKCapability",
    "is_breeze",
    "detect_capability",
    "mode_of",
    "doctor_report",
]

#: Doctor-facing names for the three exit states of the GTK behavior.
MODE_KDE_NATIVE_SYNC = "kde-native-sync"
MODE_DIRECT = "direct"
MODE_UNSUPPORTED = "unsupported"

#: Substring (case-insensitive) marking a Breeze-based GTK theme.
_BREEZE_MARKER = "breeze"


def is_breeze(theme_name: str | None) -> bool:
    """True when *theme_name* names a Breeze (or Breeze-derived) theme."""
    return bool(theme_name) and _BREEZE_MARKER in theme_name.lower()


@dataclass(frozen=True)
class GTKCapability:
    """Structured result of GTK capability detection.

    ``kde_gtk_sync_detected`` is true only when the kde-gtk-config
    mechanism is actually present on this system (``kcmshell6`` on
    PATH or the ``colorreload-gtk-module`` loaded via ``settings.ini``).
    ``direct_css_supported`` stays false while KDE owns color
    propagation: a second writer would be a configuration authority
    conflict, not a feature.
    """

    gtk3_detected: bool
    gtk4_detected: bool
    kde_gtk_sync_detected: bool
    breeze_gtk_detected: bool
    direct_css_supported: bool
    #: Documented reason when no supported behavior exists; None when
    #: the machine is served by one of the supported modes.
    reason: str | None


def detect_capability(env: GtkEnvironment) -> GTKCapability:
    """Classify *env* without touching the filesystem beyond reads."""
    gtk3 = env.has_gtk("gtk-3.0")
    gtk4 = env.has_gtk("gtk-4.0")
    sync = env.kde_gtk_integration
    breeze = is_breeze(env.gtk_theme)
    # The direct fallback's managed target is gtk-3.0/gtk.css, and it
    # is only legitimate when KDE's sync mechanism is absent.
    direct = gtk3 and not sync

    reason: str | None = None
    if not gtk3 and not gtk4:
        reason = (
            "no GTK configuration found under "
            f"{env.config_home} (no gtk-3.0, gtk-4.0)"
        )
    elif not gtk3 and not sync:
        reason = (
            "only gtk-4.0 detected and no KDE GTK integration: libadwaita "
            "apps ignore user theme CSS by design and direct generation "
            "targets gtk-3.0"
        )

    return GTKCapability(
        gtk3_detected=gtk3,
        gtk4_detected=gtk4,
        kde_gtk_sync_detected=sync,
        breeze_gtk_detected=breeze,
        direct_css_supported=direct,
        reason=reason,
    )


def mode_of(capability: GTKCapability) -> str:
    """Map a capability onto the one supported behavior for this machine."""
    if capability.kde_gtk_sync_detected and (
        capability.gtk3_detected or capability.gtk4_detected
    ):
        return MODE_KDE_NATIVE_SYNC
    if capability.direct_css_supported:
        return MODE_DIRECT
    return MODE_UNSUPPORTED


def doctor_report(env: GtkEnvironment, capability: GTKCapability) -> dict:
    """The ``omni doctor --json`` entry for the gtk adapter."""
    mode = mode_of(capability)
    notes: list[str] = []
    if mode == MODE_UNSUPPORTED:
        notes.append(capability.reason or "GTK theming unsupported")
    elif mode == MODE_KDE_NATIVE_SYNC:
        theme = env.gtk_theme
        if theme is not None and not is_breeze(theme):
            notes.append(
                f"configured GTK theme {theme!r} is not Breeze: "
                "kde-gtk-config propagates scheme colors via colors.css "
                "but does not switch the theme, so apps following it keep "
                "its own styling; Omni reports this boundary and leaves "
                "the user's theme choice untouched"
            )
        if env.colors_css("gtk-3.0") is None:
            notes.append(
                "kde-gtk-config has not written gtk-3.0/colors.css yet; "
                "applying any color scheme in System Settings triggers "
                "synchronization"
            )
    else:  # MODE_DIRECT
        notes.append(
            "direct CSS generation is available but strictly opt-in "
            "(GtkAdapter(allow_direct=True)); default behavior is "
            "observe-only and writes nothing"
        )
    return {
        "adapter": "gtk",
        "supported": mode != MODE_UNSUPPORTED,
        "mode": mode,
        "gtk3": capability.gtk3_detected,
        "gtk4": capability.gtk4_detected,
        "notes": notes,
        "config_home": str(env.config_home),
        "kde_gtk_sync_detected": capability.kde_gtk_sync_detected,
        "breeze_gtk_detected": capability.breeze_gtk_detected,
    }
