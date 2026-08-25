# The Qt/KDE theming boundary — what Omni touches and why

Session 06 scope note. This document draws the line between four
related-but-distinct concepts that are constantly confused, states
which of them Omni drives, and which files therefore remain KDE-owned
user state that Omni only ever reads.

## The four concepts

| Concept | What it styles | Where it lives | Who owns the file |
|---|---|---|---|
| **Color Scheme** (`.colors`) | Widget/app palettes for Qt and Plasma apps: window/view/button/selection color sets | `~/.local/share/color-schemes/` (packages), values copied into `~/.config/kdeglobals` when applied | Omni generates its own package (`OmniTheme.colors`); `kdeglobals` is KDE's |
| **Plasma Style** (desktoptheme) | Shell chrome: panel, plasmashell SVGs, lock screen | `~/.local/share/plasma/desktoptheme/` | Separate surface; no adapter yet |
| **Global Theme** (look-and-feel) | A *bundle*: may switch color scheme, plasma style, icons, cursors, splash, window decorations at once | `~/.local/share/plasma/look-and-feel/` | Deliberately out of scope; too coarse for semantic theming |
| **Qt application platform theme** | How a Qt app picks up platform styling at runtime (`QT_QPA_PLATFORMTHEME`, e.g. `kde6`) | Environment / `~/.config/QtProject.conf` | Neither Omni's nor directly user-edited in practice |

## Why they are not interchangeable

A Color Scheme is an INI palette. Applying one makes Plasma copy its
values into `kdeglobals`, from where running Qt applications pick them
up through the KDE platform theme plugin. A Plasma Style packages SVG
shell assets — recoloring those means editing SVGs or writing a new
style package, not choosing colors. A Global Theme is a meta-switch:
applying one may silently replace your Color Scheme *and* Plasma Style
and icons together.

Collapsing these into one "apply theme" button is exactly what makes
precise theming impossible. Omni deliberately drives **only the Color
Scheme layer**, which is the one defined by colors — the thing our
semantic model actually has.

## Safe behaviors implemented

1. Generate and install `OmniTheme.colors` (owned generated artifact).
2. Activate it with `plasma-apply-colorscheme` so *KDE itself* copies
   values into `kdeglobals` and notifies running apps.
3. Verify by reading `kdeglobals` back (read-only).
4. Rely on KDE's `kde-gtk-config` integration to propagate the same
   values to GTK (`colors.css`), verified read-only by the gtk adapter.

## Explicit non-goals

* Omni never writes `kdeglobals`, `gtkrc`, `QtProject.conf`, or any
  Plasma Style / Global Theme package.
* Omni never invokes Global Theme switching (`lookandfeeltool`,
  `plasma-apply-*` style/global-theme variants): doing so would stomp
  unrelated user settings as a side effect.
* Qt applications outside Plasma (plain `qt5ct`/`qt6ct` setups) are not
  targeted. If a future adapter adds them it must bring its own
  capability detection, ownership rules, verification and rollback —
  nothing here promises universal Qt theming.

## Rollback semantics under this boundary

Because `kdeglobals` is KDE state produced by *applying* a scheme,
rolling back means re-applying the previously active scheme package via
the native tool (the kde adapter does this), not restoring bytes into
`kdeglobals`. Files Omni truly owns (its `.colors` package, Konsole
scheme, VS Code keys, GTK direct blocks when enabled) get byte-exact
restoration; everything else is delegated back to its owner.
