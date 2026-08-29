# Adapters — the contract and the four shipped integrations

An adapter knows how one desktop surface consumes a theme. The core engine
(`core/activation.py`) drives whatever is registered through the structural
protocol in `core/adapters.py` — it never imports a concrete adapter.

## Contract

Phases, in execution order:

```
capability → plan → render → apply → verify      (activation)
rollback                                          (rollback)
```

* `capability` — pure per-machine probe returning `AdapterCapability`
  (supported + reason + version). **Unsupported is not failure**: the
  adapter is skipped and reported, and the activation still succeeds.
* `plan` — read-only intent object (what *would* happen). Must not
  side-effect.
* `render` — confirm/produce artifacts in the promoted generation
  directory (read-only w.r.t. live targets).
* `apply` — the only phase allowed external side effects.
* `verify` — read-back confirmation (hashes, kdeglobals, wallpaper).
* `rollback` — restore what this adapter owns, best-effort.

Every phase returns values (`AdapterResult`); exceptions are captured by
the engine so one broken adapter cannot take down the run.

**Criticality is explicit metadata.** A supported adapter that fails marks
the outcome DEGRADED (activation continues). Only an adapter registered
with `critical=True` triggers a deterministic rollback. As of Session 09
**no shipped adapter is registered critical** — the default registry
(`build_default_registry()`) runs:

| Order | Adapter | Surfaces |
|---|---|---|
| 1 | `kde` | Color Scheme package + wallpaper |
| 2 | `gtk` | KDE→GTK sync verification (default), opt-in direct `gtk.css` |
| 3 | `vscode` | `workbench.colorCustomizations` in `settings.json` |
| 4 | `konsole` | Konsole colorscheme + default-profile key |

Adapters receive lifecycle events via an optional `on_event(event)` hook
(`core/events.py`); one raising subscriber does not stop the others.

## KDE adapter (`adapters/kde/`)

Scope boundary (see [KDE_ADAPTER.md](KDE_ADAPTER.md) for the full verified
behaviour matrix): **Color Scheme + wallpaper only.** Plasma Style, Global
Theme, kwinrc and panels are separate surfaces — deliberately untouched
(see [qt-kde-boundary.md](qt-kde-boundary.md)).

* **Color Scheme**: the core template pipeline renders
  `~/.local/share/color-schemes/OmniTheme.colors` (a *managed target*,
  so conflict detection/rollback come for free); the adapter applies it
  with `plasma-apply-colorscheme OmniTheme` so KDE copies values into
  `kdeglobals` and notifies running apps; verifies via `kreadconfig6`
  read-back. `kdeglobals` is KDE-owned user state — read-only to us.
* **Wallpaper**: validate (magic bytes) → content-hash cache copy under
  `<state>/adapters/wallpaper-cache/` → `plasma-apply-wallpaperimage` →
  read the *active* wallpaper back (qdbus6 evaluateScript, appletsrc
  scan fallback). A journal (`<state>/adapters/kde.json`) records the
  pre-Omni wallpaper plus per-theme cache entries for rollback.
* **Rollback**: re-apply the restored generation's scheme package, then
  restore the journaled wallpaper (restored generation's theme entry →
  most recent entry → pre-Omni original). Non-image selections (e.g.
  slideshow folders) are reported and left untouched.

## GTK adapter (`adapters/gtk/`)

Strategy ladder — write only where safe:

1. **kde-sync** (preferred, automatic): with KDE's gtk integration,
   `kde-gtk-config` propagates the Color Scheme into
   `gtk-{3,4}.0/colors.css`. The adapter writes *nothing* and verifies
   the propagation instead — two owners must not fight over one file.
2. **direct** (explicit opt-in, `GtkAdapter(allow_direct=True)`): a
   marker-wrapped, journal-backed block of `--omni-*` CSS custom
   properties in `gtk-3.0/gtk.css` only. GTK4/libadwaita is *not*
   targeted — it ignores user theme CSS by design; that limitation is
   reported, never papered over. Foreign content is never merged without
   an explicit force.
3. **observe** (default without KDE integration): report capability,
   explain why nothing is written.

See [GTK.md](../user/GTK.md) for the user-facing view.

## VS Code adapter (`adapters/vscode/`)

Owns exactly one property in `<User>/settings.json`:
`workbench.colorCustomizations`, and within it only the keys in
`adapters/vscode/mapping.py:MANAGED_KEYS`. JSONC surgery preserves
comments and byte layout of everything else. Journal
(`<state>/adapters/vscode.json`) records previous values, whether
`colorCustomizations` pre-existed, and the pre-write file hash
(user-modification detection). No `_omniTheme` root key is injected —
settings.json is schema-checked by VS Code.

## Konsole adapter (`adapters/konsole/`)

The one explicitly supported terminal. Owned artifact:
`~/.local/share/konsole/OmniTheme.colorscheme` (generated). The default
profile's `[Appearance] ColorScheme=` key is edited *surgically* — every
other byte preserved verbatim, previous value + full prior bytes recorded
in `<state>/adapters/konsole.json` for exact rollback. Without a default
profile in `konsolerc` the adapter reports *unsupported* with that reason
instead of guessing which profile to edit.

## Rendering connection

Adapters 1 (`kde`) consume a *rendered managed target* declared in
`templates/targets.toml`; adapters 2–4 generate their artifacts during
`apply` from the resolved `Theme` object. Either way, ownership,
conflict detection and rollback bookkeeping live in the same core
machinery — see [ACTIVATION.md](ACTIVATION.md) and
[OWNERSHIP_AND_SECURITY.md](OWNERSHIP_AND_SECURITY.md).
