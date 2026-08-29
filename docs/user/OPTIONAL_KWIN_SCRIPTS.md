# Optional KWin Scripts — scope and status

**Status: not shipped.** No KWin scripts ship with this repository
(today there is no `hooks/` content and no `kwinrc` integration
anywhere in `core/` or `adapters/`). This page records the intended
*optional* scope so nobody expects undocumented behaviour, and the
hard boundary that will not change.

## Why "optional"

KWin scripts would exist only for window-decoration-adjacent touches
that a Color Scheme cannot express (per-window rules, scriptable
borders). They are:

* **optional** — core activation must never depend on them (control
  plane rule: optional integrations stay optional);
* **off by default** — nothing is installed or enabled unless a future,
  separately-documented session adds a `--`-gated command for it;
* **never auto-downloaded** — any future script ships in-repo and is
  installed explicitly by a named command with its own journaling and
  rollback.

## The permanent boundary (already enforced in code)

Omni does not, and will not, hand-edit `kwinrc` or window decoration
settings as part of theming:

* `kwinrc [org.kde.kdecoration2]` stays user-owned;
* no `kwriteconfig6`/`kreadconfig6` writes target kwinrc (the KDE
  adapter reads `kdeglobals` only, via `kreadconfig6`, for
  verification);
* no Global Theme / look-and-feel switching, which is the blunt
  instrument that would stomp decoration settings — see
  [`../architecture/qt-kde-boundary.md`](../architecture/qt-kde-boundary.md).

If a future session defines the KWin script scope, that decision will
land here with: what the script does, what it writes (all under the
user's own config), how to enable/disable it, and its rollback path.
Until then, treat "KWin scripts" as an unsupported feature of
omni-theme-cachy.
