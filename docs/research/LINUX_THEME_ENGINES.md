# Linux Theme Engines — Research Notes (Session 01)

Survey of adjacent projects for architectural ideas. Sources fetched August
2026 (GitHub, DeepWiki, issue trackers). We take ideas, not dependencies.

## pywal / pywal16

- Generates a 16-colour palette from an image (or uses a preset), writes
  `colors.json` + rendered files to `~/.cache/wal/`, then applies wallpaper.
- **Templates**: plain files in `~/.config/wal/templates/`, Python `str.format`
  syntax `{color0}`, `{background}`, with modifiers `{var.rgb}`, `{var.strip}`,
  `{var.rgba}`, `{var.red}` … — the same modifier idea Omarchy uses (`_strip`,
  `_rgb`).
- User templates can override built-in exports by filename.
- Original pywal is abandoned (~4+ years); maintained fork `pywal16`
  (eylles) adds `lighten/darken/saturate` template functions — evidence that a
  *colour-math layer* inside the renderer has real demand.
- Weaknesses we avoid: cache dir as runtime state (lost on reboot patterns),
  hot-reload reliance on each app watching files, no staging/atomicity.

## Stylix (NixOS)

- The most rigorous design: one global config → per-app "target" modules via a
  `mkTarget` pattern; autoloaded modules; `autoEnable` global toggle.
- Palette: Base16 standard; optional Haskell genetic-algorithm generator that
  derives a perceptually optimised palette from a wallpaper in LAB space,
  deterministic via fixed seed.
- Everything is declarative & reproducible; nothing mutates live app state —
  contrast with pywal's overwrite-in-place. Partially-applied themes are
  impossible because Nix builds first, switches atomically second.
- Lesson taken: **targets declare themselves and can be individually enabled**;
  generation and activation must be separate phases. Lesson rejected: Nix as a
  runtime dependency on an Arch system.

## Gradience

- GUI customiser for libadwaita/adw-gtk3: preset JSONs, CSS overrides,
  Material-You extraction from wallpaper. GNOME-ecosystem specific; upstream
  activity has wound down. Not portable to KDE, but validates:
  - presets as shareable data files,
  - "extract palette from wallpaper" as a user expectation,
  - CSS override escape hatch for power users.

## KDE-native tooling

- `plasma-apply-*` family (verified on this machine): colorscheme,
  desktoptheme, wallpaperimage, lookandfeel — official application layer.
- `kwriteconfig6`/`kreadconfig6`: safe atomic KConfig edits for keys no CLI
  covers (e.g. `[kdeglobals][KDE] widgetStyle`, kwin decoration keys).
- Kvantum: Qt style engine theming via `.kvconfig` + SVG assets — relevant
  later since this machine's Sweet look-and-feel sets
  `widgetStyle=kvantum`; a Kvantum adapter is feasible by generating kvconfig
  from the palette (pywal16-libadwaita proves the pipeline).
- kde-material-you-colors etc.: wallpaper→palette extraction precedent inside
  the KDE world.
- `konsave`: full-config export/import — blunt; we want per-theme ownership,
  not whole-`~/.config` snapshots.

## GTK theme tooling (for future adapters)

- GTK3/GTK4 apps read `$XDG_DATA_HOME/themes/<name>/gtk-3.0/gtk.css`;
  switching = writing `~/.config/gtk-3.0/settings.ini` (or gsettings
  `org.gnome.desktop.interface gtk-theme`) plus a generated `gtk.css`.
- adw-gtk3 + CSS variable overrides is the modern low-risk path; matches our
  generate-artifact + apply-via-official-switch philosophy.

## Cross-cutting lessons adopted

| Lesson | Origin | Where it lands in our architecture |
|--------|--------|-----------------------------------|
| Semantic palette as single source of truth | Omarchy, Stylix | `themes/*/colors.toml` |
| Placeholder modifiers (`_strip`, `_rgb`) | pywal, Omarchy | renderer filter syntax |
| Colour math (mix/lighten/darken) | pywal16, Omarchy `mix` | core colour module |
| Targets/adapters declare themselves, enableable per-app | Stylix | `adapters/` registry |
| Two-phase generate → activate | Stylix, Omarchy | staging dir + promote step |
| Hand-written overrides always win | Omarchy | precedence rules |
| Provenance-based filtering of third-party themes | Omarchy | installer policy |
| Apply through official tools only | KDE practice | adapters shell out to `plasma-apply-*` |
| Test-enforced security classification | Omarchy | tests over templates |

## Deliberately not adopted

- Nix/Home Manager as engine substrate (wrong platform).
- sed-script rendering (Python `string.Template`/custom renderer instead —
  parse errors become reportable).
- Whole-desktop snapshot managers (konsave-style) — conflicts with file
  ownership model.
