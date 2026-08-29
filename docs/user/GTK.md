# GTK Theming — what works, what doesn't

GTK on KDE is a bridge with real limits. Omni's GTK adapter
(`adapters/gtk/`) is built around one rule: **never fight KDE for
ownership of a file.** It has three modes, chosen per machine:

## Ownership map

| File | Owner | Omni's role |
| --- | --- | --- |
| generated color scheme (OmniTheme.colorscheme) | Omni | writes and verifies it |
| `~/.config/kdeglobals` | KDE | never touched by the GTK adapter |
| `~/.config/gtk-{3,4}.0/colors.css` | KDE (`kde-gtk-config`) | verified, never written |
| `~/.config/gtk-3.0/gtk.css` | you | only touched in explicit direct mode, inside a marker-wrapped managed block |

Capability detection lives in `adapters/gtk/capability.py`
(`GTKCapability` + `detect_capability`); it is read-only and treats the
live system as ground truth.

## 1. kde-sync (default when KDE integration is present)

Applying a Color Scheme makes KDE's `kde-gtk-config` propagate the same
colors into `~/.config/gtk-{3,4}.0/colors.css`. In this mode the adapter
**writes nothing** — it *verifies* the propagation instead (comparing
kdeglobals' scheme values against the generated CSS) and reports gaps as
warnings.

Verified on live Plasma 6.7: the propagation is **asynchronous** — the
daemon rewrites `colors.css` roughly 0.2 s *after* `kdeglobals` changes.
Omni's verification therefore polls inside a short window (2 s by
default) before judging; drift that persists past the window is
reported as a hard, non-silent error, never papered over.

If you see "kde-gtk-config integration detected but no gtk-3.0/colors.css
yet": open System Settings → Colors & Themes once (or apply any color
scheme) to trigger the sync, then re-run.

## 2. direct (explicit opt-in, off by default)

Without KDE integration you can enable generated CSS custom properties:

```python
from adapters.gtk import GtkAdapter
GtkAdapter(allow_direct=True)   # engine/registry construction; not a CLI flag today
```

What it does, honestly:

* writes **only** `~/.config/gtk-3.0/gtk.css`, inside a marker-wrapped
  managed block of `--omni-bg/fg/accent/selection/error/success/warning`
  variables; previous bytes are journaled (and backed up) for exact
  rollback;
* foreign content in that file is **never** merged — the adapter refuses;
  an explicit force (engine conflict policy) replaces it, with a warning;
* **GTK4 / libadwaita apps stay unstyled** — libadwaita ignores user
  theme CSS by design. The adapter reports this limitation rather than
  pretending otherwise. Use `adw-gtk3` for GTK4 look-alike coverage if
  you need it (outside Omni's scope).

Note: `allow_direct` is an adapter-construction option, **not** a CLI
flag. From the `omni` CLI the GTK adapter runs in kde-sync/observe mode
only.

## 3. observe (default without KDE integration)

Nothing is written; the capability and the reason are reported:

> no KDE GTK integration detected; GTK apps will keep their current theme

## What is explicitly unsupported

* Theming GTK4/libadwaita apps directly (they ignore user CSS).
* Writing `~/.config/gtk-4.0/gtk.css` (see above).
* gsettings/GNOME-style theme switching.
* Restarting or signaling GTK apps after a change; some GTK apps need a
  manual restart to pick up new colors — that is GTK behaviour, verified
  in `docs/research/KDE_PLASMA_6.md`, not an Omni bug.
* Overriding a deliberately chosen **non-Breeze GTK theme**: verified
  on live Plasma 6.7, `kde-gtk-config` propagates scheme colors into
  `colors.css` even then, but it does **not** switch your theme — apps
  following e.g. WhiteSur keep that theme's own styling. Omni reports
  this boundary — in activation warnings and in `omni doctor` notes —
  and leaves your theme choice untouched. It never force-switches you
  to Breeze.

`omni doctor --json | jq .adapter_capabilities.gtk` shows what was
detected, classified into one of three modes:

* `"kde-native-sync"` — KDE owns the chain; Omni verifies only;
* `"direct"` — generation available, strictly opt-in;
* `"unsupported"` — with a documented reason in `notes`.

The entry also reports `gtk3`/`gtk4` detection and any boundary notes
(non-Breeze theme, colors.css not yet written, direct-mode opt-in
reminder). There is no mode in which Omni's GTK changes work only until
the next login: either KDE persists them (kde-sync) or Omni's writes are
marker-owned, journalled, and rollback-exact (direct).
