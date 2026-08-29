# Optional KWin Scripts — scope and status

**Status: not shipped.** No KWin scripts ship with this repository
(today there is no `hooks/` content and no `kwinrc` integration
anywhere in `core/` or `adapters/`). This page records the intended
*optional* scope so nobody expects undocumented behaviour, and the
hard boundary that will not change.

**Omni does not install or manage window-tiling behaviour.** The theme
engine's scope is colors, wallpapers, terminal and editor appearance —
not window management. Omni targets KDE Plasma 6 with KWin's
traditional floating-window workflow and mouse-driven desktop usage.
A normal `omni theme apply default --yes` does not install packages,
enable KWin scripts, change tiling behaviour, or replace KWin.

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

## No package installation

The engine never invokes a package manager. No code path in `core/`,
`adapters/`, `hooks/` or `scripts/` runs `pacman`, `yay`, `paru`, `dnf`,
`apt`, `zypper`, `flatpak` or `snap`, and nothing installs AUR or
system packages automatically (verified by the session 16 scope-hygiene
scan; see
[`../architecture/OWNERSHIP_AND_SECURITY.md`](../architecture/OWNERSHIP_AND_SECURITY.md)).
`install.sh` likewise contains no package-manager calls — it only
creates a dedicated venv and `pip install .` into it. If your desktop
is missing a prerequisite (e.g. `kreadconfig6`), install it yourself
with your distribution's normal tooling.

## Window behaviour settings

The engine has no window-behaviour settings today. In particular,
`BorderlessMaximizedWindows` does not appear anywhere in the code,
templates or themes — maximized-window decoration behaviour stays
exactly where KWin puts it. If a future session ever adds such a
setting, it must be: explicitly opt-in, parsed through
`core/kde_config.py`, reversible via rollback, documented here, and
never applied as part of ordinary theme activation. Until then there
is nothing to configure.

## Community tiling scripts (out of scope, not endorsed)

Community tiling/window-management scripts — e.g. Krohnkite, Kzones,
Polonium, PlasmaZones — are **out of scope** for the theme engine.
Omni neither ships, installs, enables, nor configures them. If you
want tiling, you install and manage such scripts yourself through
System Settings → KWin Scripts or your distribution's packages.

For reference only, the upstream locations of the commonly named
community scripts (verified via web search, August 2026):

| Script | Upstream (verified 2026-08) |
|---|---|
| Krohnkite | <https://github.com/esjeon/krohnkite> |
| Kzones | <https://github.com/gerritdevriese/kzones> |
| Polonium | <https://github.com/zeroxoneafour/polonium> (upstream announced the project's end in Aug 2024; check the repo for current status) |
| PlasmaZones | <https://github.com/fuddlesworth/PlasmaZones> |

**No endorsement, no security review.** This listing is a pointer, not
a recommendation. Omni makes no claim about the quality, maintenance
status, security, or privacy of these third-party projects, reviews
none of their code, and accepts no responsibility for what they do to
your session. Evaluate them yourself before installing. Names and URLs
may be stale by the time you read this; treat the repositories as the
source of truth, not this page.
