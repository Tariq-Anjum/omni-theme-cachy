# GTK Theming — what works, what doesn't

GTK on KDE is a bridge with real limits. Omni's GTK adapter
(`adapters/gtk/`) is built around one rule: **never fight KDE for
ownership of a file.** It has three modes, chosen per machine:

## 1. kde-sync (default when KDE integration is present)

Applying a Color Scheme makes KDE's `kde-gtk-config` propagate the same
colors into `~/.config/gtk-{3,4}.0/colors.css` / `gtk.css`. In this mode
the adapter **writes nothing** — it *verifies* the propagation instead
(comparing kdeglobals' scheme values against the generated CSS) and
reports gaps as warnings.

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

`omni doctor --json | jq .adapter_capabilities.gtk` shows what was
detected: installed GTK dirs, whether kde-gtk integration is active, and
your config home.
