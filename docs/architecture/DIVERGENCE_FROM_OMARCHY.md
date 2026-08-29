# Divergence from Omarchy — borrowed ideas and deliberate differences

Omni Theme Cachy is *inspired by* the Omarchy theming engine
(`basecamp/omarchy`, `quattro` branch) but is a different system for a
different desktop. Grounding: `docs/research/OMARCHY_ARCHITECTURE.md` and
`docs/research/OMARCHY_THEMING.md` were verified against the upstream
repository (read directly, August 2026). Anything below that is design
aspiration rather than verified upstream fact is labelled
*inspiration, not verified*.

## Borrowed architectural ideas

| Omarchy idea | Where it lands in Omni |
|---|---|
| One semantic `colors.toml` per theme, canonical roles over app-specific slots | `themes/*/colors.toml`, `SEMANTIC_ROLES` in `core/theme_model.py` |
| Surfaces file separated from the palette (`shell.toml`) | `surfaces.toml` (`popups`, `controls` groups; alpha companions, gradients, border-width lists) |
| Template-driven rendering of app configs from the palette | `core/renderer.py` (`{{ key }}`, `_strip`, `_rgb`, `mix`, gradients) |
| User overlay wins over system theme; whole-file, staged at generation time | `load_theme_with_overlay()` deep merge of `~/.config/omni-theme/themes/<name>/` |
| User templates beat built-ins (same output name ⇒ built-in skipped) | template resolution order in `core/staging.py` |
| `next-*` staging + atomic promotion; consumers never see torn state | generations + atomic symlink swap (`core/state.py`) |
| Lock the switch so concurrent runs serialize | (in spirit) single-state-dir staging; *upstream uses a `flock`; Omni does not yet add a cross-process lock* |
| Post-promotion hooks keep adapters decoupled | lifecycle events (`core/events.py`); a `hooks/` directory is reserved |
| Semantic palette + templates + `--yes`-style non-interactive ergonomics | `omni` CLI with stable exit codes and `--json` everywhere |
| Security stance: themes are data; provenance filtering planned | inert template grammar + declared targets shipped; *installer + denylist filtering not yet implemented* (see OWNERSHIP_AND_SECURITY.md) |

Per the Session 09 note on Omarchy Quattro: its theme staging, user theme
overlays, user-wide templates, semantic `colors.toml` and `shell.toml`
surface/style roles inspire the theme-generation layer here; its Quickshell
shell is a separate system and is not used.

## What is deliberately NOT borrowed

* **Hyprland** — no tiling assumptions, no `hyprctl reload`, no Hyprland
  Lua modules. Omni targets KDE Plasma 6's own layers (Color Scheme,
  wallpaper) via KDE's official tools.
* **Quickshell / the QML shell** — no shell replacement, no IPC theme push
  (`omarchy-shell shell applyTheme`), no `shell.json`/plugin manifest
  system. Plasma stays Plasma; Omni does not duplicate or replace
  `shell.json` in any form.
* **Hyprland IPC / OSC live retinting of every open pane** — Plasma's
  `plasma-apply-*` tools already notify running apps; where a surface
  needs a restart, that is the surface's documented behaviour (e.g.
  Konsole picks up a re-applied scheme; GTK apps partially need restart —
  see `docs/research/KDE_PLASMA_6.md`).
* **The sed-script renderer** — replaced by a parsed, strict template
  engine so errors are reportable (`tomllib` + closed helpers, zero deps).
* **`light.mode` marker-file legacy** — `mode = "dark"|"light"` in TOML
  only.
* **Whole-desktop snapshot switching** — Omni records per-target
  ownership hashes instead of snapshotting `~/.config`.

## Where Omni goes further

* **Validation as data**: WCAG 2.x contrast thresholds, required-role
  checks and strict surface-value grammar (`omni theme validate`).
* **Generations + explicit rollback**: immutable snapshots, pointer swaps,
  byte-exact materialization of owned targets (upstream keeps a single
  `current/theme` and accepts an rm→mv micro-gap — *inspiration, not
  verified as a defect*).
* **Adapter contract**: capability probes, skip-and-report semantics,
  explicit criticality, per-phase results — an unsupported surface must
  not fail the activation.
* **Desktop boundary discipline**: documented Qt/KDE ownership boundary
  (`qt-kde-boundary.md`); Omni never touches `kdeglobals` by hand,
  Plasma Style, Global Themes or kwinrc.

## Compatibility note

The `colors.toml` convention is shared with Omarchy-style themes, so an
Omarchy palette can be dropped into `themes/<name>/colors.toml` and parsed
directly (`tomllib`), subject to Omni's required-role validation — a theme
needs the full semantic role set (see [THEME_MODEL.md](THEME_MODEL.md))
before it will validate.
